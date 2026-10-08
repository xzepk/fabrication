using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RhinoAi.Contracts;
using RhinoAi.Core;

var moduleRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../"));
var configuration = new DirectoryInfo(AppContext.BaseDirectory).Parent!.Name;
var dotnet = Path.GetFullPath(args.Length > 0 ? args[0] : Environment.GetEnvironmentVariable("DOTNET") ?? Environment.ProcessPath!);
var hostDll = Path.GetFullPath(args.Length > 1 ? args[1] : Path.Combine(moduleRoot, "src", "RhinoAi.Host", "bin", configuration, "net8.0", "RhinoAi.Host.dll"));
var evidenceDirectory = args.Length > 2 ? Path.GetFullPath(args[2]) : Path.GetFullPath("artifacts/host-integration");
Directory.CreateDirectory(evidenceDirectory);
var work = Path.Combine(Path.GetTempPath(), "rhinoai-host-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(work);
var results = new List<object>();
var failed = 0;
var state = Path.Combine(work, "state");
HostProcess host = await HostProcess.Start(dotnet, hostDll, state);
try
{
    await Test("authenticated health and REVIEW status", async () => { var r = await host.Client.GetAsync("health"); await Status(r, 200); Assert((await r.Content.ReadAsStringAsync()).Contains("REVIEW"), "Missing review status"); });
    await Test("short startup nonce fails closed", async () => { await HostProcess.AssertStartupFails(dotnet, hostDll, Path.Combine(work, "bad-nonce"), validNonce: false); });
    await Test("missing bearer nonce denied", async () => { using var client = host.NewClient(false); await Status(await client.GetAsync("health"), 401); });
    await Test("incorrect bearer nonce denied", async () => { using var client = host.NewClient(false); client.DefaultRequestHeaders.Authorization = new("Bearer", new string('x', 43)); await Status(await client.GetAsync("health"), 401); });
    await Test("Origin header denied even with valid auth", async () => { using var request = new HttpRequestMessage(HttpMethod.Get, "health"); request.Headers.TryAddWithoutValidation("Origin", "https://example.test"); await Status(await host.Client.SendAsync(request), 403); });
    await Test("external Host header denied", async () => { using var request = new HttpRequestMessage(HttpMethod.Get, "health"); request.Headers.Host = "evil.example:" + host.Port; await Status(await host.Client.SendAsync(request), 403); });
    await Test("wrong loopback Host port denied", async () => { using var request = new HttpRequestMessage(HttpMethod.Get, "health"); request.Headers.Host = "127.0.0.1:1"; await Status(await host.Client.SendAsync(request), 403); });
    await Test("external URL config cannot change loopback bind", async () => { Assert(host.Output.Contains("http://127.0.0.1:" + host.Port), "No literal-loopback startup evidence"); await Status(await host.Client.GetAsync("health"), 200); });
    await Test("unknown endpoint and arbitrary code endpoint denied", async () => { await Status(await host.Client.PostAsync("v1/execute", Json("{}")), 404); await Status(await host.Client.PostAsync("v1/export", Json("{}")), 404); await Status(await host.Client.PostAsync("v2/prepare", Json("{}")), 404); });
    await Test("invalid operation UUID rejected", async () => { await Status(await host.Client.GetAsync("v1/operations/not-a-uuid"), 400); });
    await Test("unknown operation gives typed not-found", async () => { await Status(await host.Client.GetAsync("v1/operations/" + Guid.NewGuid()), 404); });
    await Test("wrong Content-Type rejected", async () => { await Status(await host.Client.PostAsync("v1/prepare", new StringContent("{}")), 415); });
    await Test("content-encoded body rejected", async () => { using var content = Json("{}"); content.Headers.ContentEncoding.Add("gzip"); await Status(await host.Client.PostAsync("v1/prepare", content), 415); });
    await Test("oversize Content-Length rejected", async () => { await Status(await host.Client.PostAsync("v1/prepare", Json(new string(' ', 1_048_577))), 413); });
    await Test("oversize chunked body rejected", async () => { using var request = new HttpRequestMessage(HttpMethod.Post, "v1/prepare") { Content = Json(new string(' ', 1_048_577)) }; request.Headers.TransferEncodingChunked = true; await Status(await host.Client.SendAsync(request), 413); });
    await Test("malformed JSON rejected", async () => { await Status(await host.Client.PostAsync("v1/prepare", Json("{oops")), 400); });
    await Test("null and missing required fields rejected", async () => { await Status(await host.Client.PostAsync("v1/prepare", Json("null")), 400); await Status(await host.Client.PostAsync("v1/prepare", Json("{}")), 400); });
    await Test("unknown JSON fields rejected", async () => { var body = JsonSerializer.SerializeToNode(Input(), Protocol.Json)!.AsObject(); body["arbitraryCode"] = "malicious()"; await Status(await host.Client.PostAsync("v1/prepare", Json(body.ToJsonString())), 400); });
    await Test("duplicate JSON keys rejected", async () => { var body = JsonSerializer.Serialize(Input(), Protocol.Json); body = body.Insert(1, "\"request\": null,"); await Status(await host.Client.PostAsync("v1/prepare", Json(body)), 400); });
    await Test("missing scalar DTO fields do not silently default", async () => { var body = JsonSerializer.SerializeToNode(Input(), Protocol.Json)!.AsObject(); body["snapshot"]!.AsObject().Remove("revision"); await Status(await host.Client.PostAsync("v1/prepare", Json(body.ToJsonString())), 400); });
    await Test("wrong JSON property case rejected", async () => { var body = JsonSerializer.Serialize(Input(), Protocol.Json).Replace("\"toolId\"", "\"ToolId\""); await Status(await host.Client.PostAsync("v1/prepare", Json(body)), 400); });
    await Test("unsupported protocol rejected", async () => { var input = Input(); await Status(await PostPrepare(input with { Request = input.Request with { ProtocolVersion = 99 } }), 400); });
    await Test("unsupported tool rejected", async () => { var input = Input(); await Status(await PostPrepare(input with { Request = input.Request with { ToolId = "python.exec" } }), 400); });
    await Test("invalid geometry and stale context rejected", async () => { var input = Input(); await Status(await PostPrepare(input with { Request = input.Request with { Box = input.Request.Box! with { Width = -1 } } }), 400); await Status(await PostPrepare(input with { Request = input.Request with { Expected = input.Request.Expected with { Revision = 10 } } }), 400); });
    await Test("numeric operation enums rejected", async () => { await Status(await host.Client.PostAsync("v1/complete", Json("{\"operationId\":\"" + Guid.NewGuid() + "\",\"requestHash\":\"hash\",\"state\":1}")), 400); });

    var primary = Input();
    ChangePlan? primaryPlan = null;
    await Test("prepare persists detached plan and before checkpoint", async () => { primaryPlan = await Prepare(primary); var record = await Get(primary.Request.OperationId); Assert(record.State == OperationState.Prepared && record.BeforeCheckpoint?.Snapshot.SnapshotHash == primary.Snapshot.SnapshotHash, "Prepared state/checkpoint missing"); });
    await Test("numeric NaN and null entity entries rejected", async () => { var body = JsonSerializer.Serialize(Input(), Protocol.Json).Replace("\"width\": 10", "\"width\": NaN"); await Status(await host.Client.PostAsync("v1/prepare", Json(body)), 400); var input = Input(); var altered = input.Snapshot with { Entities = [null!] }; await Status(await PostPrepare(new(input.Request, altered)), 400); });
    await Test("same operation/hash deduplicates concurrent retries", async () => { var first = await Get(primary.Request.OperationId); var replies = await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => Prepare(primary))); Assert(replies.All(x => x.RequestHash == primaryPlan!.RequestHash), "Hash changed"); Assert((await Get(primary.Request.OperationId)).UpdatedAt == first.UpdatedAt, "Retry rewrote record"); });
    await Test("same operation changed payload rejected", async () => { await Status(await PostPrepare(primary with { Request = primary.Request with { Box = primary.Request.Box! with { Width = 11 } } }), 409); });
    await Test("commit without applying acknowledgement rejected", async () => { await Status(await Complete(primaryPlan!, OperationState.Committed, AddedOutcome(primaryPlan!)), 409); });
    await Test("applying acknowledgement durably persisted before mutation", async () => { await Status(await Complete(primaryPlan!, OperationState.Applying), 200); Assert((await Get(primary.Request.OperationId)).State == OperationState.Applying, "Not applying"); var json = await File.ReadAllTextAsync(Path.Combine(state, "journal-v1.json")); Assert(json.Contains("Applying") && json.Contains("Running"), "Operation/task transition missing on disk"); });
    await Test("concurrent same-document applying blocked", async () => { var other = primary with { Request = primary.Request with { OperationId = Guid.NewGuid(), EntityId = "SECOND" } }; var plan = await Prepare(other); await Status(await Complete(plan, OperationState.Applying), 409); });
    await Test("arbitrary post-applying cancellation rejected", async () => { await Status(await Complete(primaryPlan!, OperationState.Cancelled), 409); });
    await Test("invalid completion cannot claim commit", async () => { await Status(await Complete(primaryPlan!, OperationState.Committed, AddedOutcome(primaryPlan!) with { UndoRecord = 0 }), 400); });
    var outcome = AddedOutcome(primaryPlan!);
    await Test("verified completion committed", async () => { await Status(await Complete(primaryPlan!, OperationState.Committed, outcome), 200); Assert((await Get(primary.Request.OperationId)).State == OperationState.Committed, "Not committed"); });
    await Test("lost completion ACK retry returns identical stored outcome", async () => { var first = await Get(primary.Request.OperationId); await Status(await Complete(primaryPlan!, OperationState.Committed, outcome), 200); var second = await Get(primary.Request.OperationId); Assert(Protocol.Hash(first) == Protocol.Hash(second), "Retry changed stored outcome"); });
    await Test("same terminal state changed outcome rejected", async () => { await Status(await Complete(primaryPlan!, OperationState.Committed, outcome with { UndoRecord = 9 }), 409); });
    await Test("committed record cannot replay applying", async () => { await Status(await Complete(primaryPlan!, OperationState.Applying), 409); });
    await Test("restart preserves completed operation and changes session nonce", async () => { var first = await Get(primary.Request.OperationId); var oldNonce = host.Nonce; host.Dispose(); host = await HostProcess.Start(dotnet, hostDll, state); Assert(host.Nonce != oldNonce, "Nonce reused"); Assert(Protocol.Hash(first) == Protocol.Hash(await Get(primary.Request.OperationId)), "Restart changed completion"); using var oldClient = host.NewClient(false); oldClient.DefaultRequestHeaders.Authorization = new("Bearer", oldNonce); await Status(await oldClient.GetAsync("health"), 401); });
    var ambiguous = await Prepare(Input());
    await Test("restart quarantines interrupted applying", async () => { await Status(await Complete(ambiguous, OperationState.Applying), 200); host.Dispose(); host = await HostProcess.Start(dotnet, hostDll, state); Assert((await Get(ambiguous.Request.OperationId)).State == OperationState.FailedRecovery, "Interrupted operation not quarantined"); await Status(await PostPrepare(new(ambiguous.Request, ambiguous.Before)), 409); });
    await Test("new operations blocked until document recovery reconciled", async () => { var request = ambiguous.Request with { OperationId = Guid.NewGuid(), EntityId = "NEXT" }; await Status(await PostPrepare(new(request, ambiguous.Before)), 409); });
    await Test("durable plugin completion reconciles host crash without reapply", async () => { await Status(await Complete(ambiguous, OperationState.Committed, AddedOutcome(ambiguous)), 200); Assert((await Get(ambiguous.Request.OperationId)).State == OperationState.Committed, "Reconciliation failed"); });
    await Test("proven pre-mutation cancellation reconciles applying", async () => { var plan = await Prepare(Input()); await Status(await Complete(plan, OperationState.Applying), 200); await Status(await Complete(plan, OperationState.Cancelled, error: "Cancelled before document mutation."), 200); });
    await Test("prepared reject and cancel are terminal", async () => { var reject = await Prepare(Input()); await Status(await Complete(reject, OperationState.Rejected, error: "Preview rejected."), 200); await Status(await Complete(reject, OperationState.Applying), 409); var cancel = await Prepare(Input()); await Status(await Complete(cancel, OperationState.Cancelled), 200); await Status(await Complete(cancel, OperationState.Applying), 409); });
    await Test("checkpoint restore verifies effect and survives restart", async () => { var before = outcome.After; var target = new Checkpoint(Guid.NewGuid(), before.DocumentId, DateTimeOffset.UtcNow, primary.Snapshot); var request = new ToolRequest(1, Guid.NewGuid(), Guid.NewGuid(), "checkpoint.restore", PlanValidator.Expected(before), CheckpointId: target.CheckpointId); var plan = await Prepare(new(request, before, target)); await Status(await Complete(plan, OperationState.Applying), 200); var restored = new ApplyOutcome(before with { Revision = before.Revision + 1, Entities = [] }, [], [], before.Entities.Select(x => x.RhinoId).ToArray(), 2, []); await Status(await Complete(plan, OperationState.Committed, restored), 200); host.Dispose(); host = await HostProcess.Start(dotnet, hostDll, state); Assert((await Get(request.OperationId)).State == OperationState.Committed, "Restore record did not persist"); });
    await Test("translation verifies changed fingerprint and preserves business identity", async () => { var source = Input().Snapshot with { Entities = [outcome.After.Entities[0]] }; var objectId = source.Entities[0].RhinoId; var request = new ToolRequest(1, Guid.NewGuid(), Guid.NewGuid(), "object.translate", PlanValidator.Expected(source), ObjectId: objectId, Translation: new(5, 0, 0)); var plan = await Prepare(new(request, source)); await Status(await Complete(plan, OperationState.Applying), 200); var changed = source.Entities[0] with { Fingerprint = "translated-fingerprint", GeometryJson = "{\"translated\":true}" }; var after = new ApplyOutcome(source with { Revision = source.Revision + 1, Entities = [changed] }, [], [objectId], [], 3, []); await Status(await Complete(plan, OperationState.Committed, after with { Modified = [] }), 400); await Status(await Complete(plan, OperationState.Committed, after), 200); });
    await Test("checkpoint restore changed target under same ID conflicts", async () => { var snapshot = Input().Snapshot; var checkpoint = new Checkpoint(Guid.NewGuid(), snapshot.DocumentId, DateTimeOffset.UtcNow, snapshot); var request = new ToolRequest(1, Guid.NewGuid(), Guid.NewGuid(), "checkpoint.restore", PlanValidator.Expected(snapshot), CheckpointId: checkpoint.CheckpointId); await Prepare(new(request, snapshot, checkpoint)); await Status(await PostPrepare(new(request, snapshot, checkpoint with { CreatedAt = checkpoint.CreatedAt.AddSeconds(1) })), 409); });
    await Test("malformed journal fails closed without automatic reset", async () => { var bad = Path.Combine(work, "malformed-journal"); Directory.CreateDirectory(bad); await File.WriteAllTextAsync(Path.Combine(bad, "journal-v1.json"), "{not-json"); await HostProcess.AssertStartupFails(dotnet, hostDll, bad); Assert(await File.ReadAllTextAsync(Path.Combine(bad, "journal-v1.json")) == "{not-json", "Corrupt evidence overwritten"); });
    await Test("unknown and corrupt journals fail closed at startup", async () => { var badState = Path.Combine(work, "corrupt"); Directory.CreateDirectory(badState); await File.WriteAllTextAsync(Path.Combine(badState, "journal-v1.json"), "{\"formatVersion\":99,\"operations\":[],\"tasks\":[]}"); await HostProcess.AssertStartupFails(dotnet, hostDll, badState); });
    await Test("second host cannot share the journal writer lease", async () => { await HostProcess.AssertStartupFails(dotnet, hostDll, state); });
    await Test("nonce never persisted or logged", async () => { Assert(!host.Output.Contains(host.Nonce, StringComparison.Ordinal), "Nonce logged"); foreach (var file in Directory.GetFiles(state)) { if (Path.GetExtension(file) == ".json") Assert(!(await File.ReadAllTextAsync(file)).Contains(host.Nonce, StringComparison.Ordinal), "Nonce persisted"); } });
    await Test("storage failure refuses success and quarantines health", async () => { var moved = state + "-offline"; Directory.Move(state, moved); await File.WriteAllTextAsync(state, "blocked"); try { await Status(await PostPrepare(Input()), 503); await Status(await host.Client.GetAsync("health"), 503); } finally { File.Delete(state); Directory.Move(moved, state); } });
}
finally { host.Dispose(); }
var summary = new { schemaVersion = 1, timestamp = DateTimeOffset.UtcNow, environment = RuntimeInformation.OSDescription, dotnet = Environment.Version.ToString(), hostBinary = hostDll, hostSha256 = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(hostDll))), liveRhino = "NOT_RUN: Headless HTTP process tests do not execute RhinoCommon or native Undo/Redo.", passed = results.Count - failed, failed, tests = results };
await File.WriteAllTextAsync(Path.Combine(evidenceDirectory, "results.json"), JsonSerializer.Serialize(summary, Protocol.Json));
Console.WriteLine($"Host HTTP integration: {results.Count - failed} PASS, {failed} FAIL. Live Rhino: NOT_RUN.");
return failed == 0 ? 0 : 1;

async Task Test(string name, Func<Task> action)
{
    try { await action(); results.Add(new { name, status = "PASS" }); Console.WriteLine("PASS " + name); }
    catch (Exception ex) { failed++; results.Add(new { name, status = "FAIL", error = ex.Message }); Console.WriteLine("FAIL " + name + ": " + ex.Message); }
}
Task<HttpResponseMessage> PostPrepare(PrepareRequest input) => host.Client.PostAsJsonAsync("v1/prepare", input, Protocol.Json);
async Task<ChangePlan> Prepare(PrepareRequest input) { using var r = await PostPrepare(input); await Status(r, 200); return (await r.Content.ReadFromJsonAsync<ChangePlan>(Protocol.Json))!; }
async Task<OperationRecord> Get(Guid id) { using var r = await host.Client.GetAsync("v1/operations/" + id); await Status(r, 200); return (await r.Content.ReadFromJsonAsync<OperationRecord>(Protocol.Json))!; }
Task<HttpResponseMessage> Complete(ChangePlan plan, OperationState operationState, ApplyOutcome? value = null, string? error = null) => host.Client.PostAsJsonAsync("v1/complete", new CompleteRequest(plan.Request.OperationId, plan.RequestHash, operationState, value, error), Protocol.Json);
static StringContent Json(string body) => new(body, Encoding.UTF8, "application/json");
static void Assert(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
static async Task Status(HttpResponseMessage response, int expected)
{
    var text = await response.Content.ReadAsStringAsync();
    Assert((int)response.StatusCode == expected, $"Expected HTTP {expected}, got {(int)response.StatusCode}: {text}");
    if (expected >= 400) { var error = JsonSerializer.Deserialize<ApiError>(text, Protocol.Json); Assert(!string.IsNullOrWhiteSpace(error?.Code) && !string.IsNullOrWhiteSpace(error?.Message), "Error DTO missing"); }
}
static PrepareRequest Input()
{
    var snapshot = new DocumentSnapshot(Guid.NewGuid(), Guid.NewGuid(), 0, "Millimeters", 0.01, [], []);
    var request = new ToolRequest(1, Guid.NewGuid(), Guid.NewGuid(), "box.add", PlanValidator.Expected(snapshot), new BoxSpec(new(0, 0, 0), 10, 20, 30), EntityId: "BOX-001");
    return new(request, snapshot);
}
static ApplyOutcome AddedOutcome(ChangePlan plan)
{
    var entity = new EntitySnapshot(Guid.NewGuid(), plan.Request.EntityId!, "detached-test-fingerprint", "{\"testBox\":true}", "{}", "Brep", true);
    return new(plan.Before with { Revision = plan.Before.Revision + 1, Entities = [.. plan.Before.Entities, entity] }, [entity.RhinoId], [], [], 1, []);
}

sealed class HostProcess : IDisposable
{
    private readonly Process process;
    private bool disposed;
    private readonly StringBuilder output = new();
    public string Output { get { lock (output) return output.ToString(); } }
    public string Nonce { get; }
    public int Port { get; }
    public HttpClient Client { get; }
    private HostProcess(string dotnet, string hostDll, string stateDirectory, bool validNonce = true)
    {
        var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start(); Port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
        Nonce = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var start = new ProcessStartInfo(dotnet) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add(hostDll);
        start.Environment["RHINOAI_SESSION_NONCE"] = validNonce ? Nonce : "invalid";
        start.Environment["RHINOAI_PORT"] = Port.ToString();
        start.Environment["RHINOAI_STATE_DIR"] = stateDirectory;
        // This configuration is untrusted and must never enable an external listener.
        start.Environment["ASPNETCORE_URLS"] = "http://0.0.0.0:49999";
        process = Process.Start(start) ?? throw new InvalidOperationException("Could not start actual Host process");
        start.Environment.Remove("RHINOAI_SESSION_NONCE");
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) lock (output) output.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) lock (output) output.AppendLine(e.Data); };
        process.BeginOutputReadLine(); process.BeginErrorReadLine();
        Client = NewClient(true);
    }
    public HttpClient NewClient(bool authenticate)
    {
        var client = new HttpClient(new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false }) { BaseAddress = new Uri($"http://127.0.0.1:{Port}/"), Timeout = TimeSpan.FromSeconds(10) };
        if (authenticate) client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", Nonce);
        return client;
    }
    public static async Task<HostProcess> Start(string dotnet, string hostDll, string stateDirectory)
    {
        var host = new HostProcess(dotnet, hostDll, stateDirectory);
        try
        {
            for (var attempt = 0; attempt < 100; attempt++)
            {
                if (host.process.HasExited) throw new InvalidOperationException("Host failed startup: " + host.Output);
                try { using var response = await host.Client.GetAsync("health"); if (response.IsSuccessStatusCode) return host; } catch (HttpRequestException) { }
                await Task.Delay(50);
            }
            throw new TimeoutException("Host startup timed out: " + host.Output);
        }
        catch { host.Dispose(); throw; }
    }
    public static async Task AssertStartupFails(string dotnet, string hostDll, string stateDirectory, bool validNonce = true)
    {
        using var host = new HostProcess(dotnet, hostDll, stateDirectory, validNonce);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await host.process.WaitForExitAsync(timeout.Token);
        if (host.process.ExitCode == 0) throw new InvalidOperationException("Invalid startup configuration was accepted");
    }
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        Client.Dispose();
        if (!process.HasExited) { process.Kill(entireProcessTree: true); process.WaitForExit(5000); }
        process.Dispose();
    }
}
