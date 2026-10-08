using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RhinoAi.Contracts;
using RhinoAi.Core;
using RhinoAi.Host;

if (args.Length is < 2 or > 3) { Console.Error.WriteLine("Usage: RhinoAi.Cladding.Tests <moduleRoot> <evidenceDirectory> [skillPython]"); return 2; }
var module = Path.GetFullPath(args[0]);
var evidence = Path.GetFullPath(args[1]);
var python = args.Length == 3 ? Path.GetFullPath(args[2]) : null;
Directory.CreateDirectory(evidence);
var work = Path.Combine(evidence, "cladding-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(work);
var adapter = Path.Combine(module, "adapters", "cladding");
var skill = Path.GetFullPath(Path.Combine(module, "..", "cladding-delivery"));
var settings = new CladdingAdapterSettings(python, python is null ? null : skill, adapter, Path.Combine(work, "state"));
using var service = new CladdingReviewService(settings);
var results = new List<object>(); var failed = 0;
await Test("explicit plate inputs and capability manifest", () => { CladdingReviewValidator.Validate(Input()); var json = JsonSerializer.Serialize(service.Capabilities()); Assert(json.Contains("NOT_RELEASED") && json.Contains("selected_managed"), "capability missing"); return Task.CompletedTask; });
await Test("missing material and zero density rejected", () => { var r = Input(); Reject(() => CladdingReviewValidator.Validate(r with { Components = [r.Components[0] with { Material = "" }] })); Reject(() => CladdingReviewValidator.Validate(r with { Components = [r.Components[0] with { DensityKgM3 = 0 }] })); return Task.CompletedTask; });
await Test("unsupported folds tubes rotations quantity units rejected", () => { var r = Input(); foreach (var c in new[] { r.Components[0] with { Features = ["holes"] }, r.Components[0] with { GeometryType = "rect_tube" }, r.Components[0] with { Plane = "ROTATED" }, r.Components[0] with { Quantity = 2 } }) Reject(() => CladdingReviewValidator.Validate(r with { Components = [c] })); var s = r.Snapshot with { Units = "Meters" }; Reject(() => CladdingReviewValidator.Validate(r with { Snapshot = s, Expected = PlanValidator.Expected(s) })); return Task.CompletedTask; });
await Test("explicit dimensions and identity fail closed", () => { var r = Input(); foreach (var c in new[] { r.Components[0] with { WidthMM = double.NaN }, r.Components[0] with { ThicknessMM = 0.001 }, r.Components[0] with { EntityId = "../escape" }, r.Components[0] with { OriginMM = new(1e9, 0, 0) } }) Reject(() => CladdingReviewValidator.Validate(r with { Components = [c] })); Reject(() => CladdingReviewValidator.Validate(r with { Components = [r.Components[0], r.Components[0] with { EntityId = r.Components[0].EntityId.ToLowerInvariant() }] })); return Task.CompletedTask; });
await Test("selection source exactness and explicit adopted remeasurement", () => { var r = Selected(); CladdingReviewValidator.Validate(r); var c = r.Components[0] with { WidthMM = 805, Measurements = [new("widthMM", 800, 805, 805, "Explicit test survey adoption")] }; CladdingReviewValidator.Validate(r with { Components = [c] }); Reject(() => CladdingReviewValidator.Validate(r with { Components = [c with { Measurements = null }] })); Reject(() => CladdingReviewValidator.Validate(r with { Components = [c with { Measurements = [new("widthMM", 799, 805, 805, "Test")] }] })); Reject(() => CladdingReviewValidator.Validate(r with { Sources = [r.Sources[0] with { Fingerprint = "changed" }] })); return Task.CompletedTask; });
await Test("target omission stale context and wrong used value rejected", () => { var r = Input(); Reject(() => CladdingReviewValidator.Validate(r with { Targets = ["step"] })); Reject(() => CladdingReviewValidator.Validate(r with { Expected = r.Expected with { Revision = 99 } })); Reject(() => CladdingReviewValidator.Validate(r with { Components = [r.Components[0] with { Measurements = [new("widthMM", 800, 810, 810, "Test")] }] })); return Task.CompletedTask; });
await Test("strict JSON rejects unknown duplicate and missing engineering fields", () => { var json = JsonSerializer.Serialize(Input(), Protocol.Json); RejectJson(() => StrictJson.Parse<CladdingReviewRequest>(json.Replace("\"grade\": \"3003-H24\",", ""))); RejectJson(() => StrictJson.Parse<CladdingReviewRequest>(json.Replace("\"quantity\": 1", "\"quantity\": 1, \"execute\": \"bad\""))); RejectJson(() => StrictJson.Parse<CladdingReviewRequest>(json.Replace("\"quantity\": 1", "\"quantity\": 1, \"quantity\": 2"))); return Task.CompletedTask; });
await Test("deterministic provider cleanup race tolerated only by running quota scan", async () =>
{
    foreach (var running in new[] { true, false })
    {
        var root = Path.Combine(work, "cleanup-queued-" + running); var child = Path.Combine(root, "_provider", "P-001");
        Directory.CreateDirectory(child); File.WriteAllText(Path.Combine(child, "temporary.step"), "temporary"); File.WriteAllText(Path.Combine(root, "kept.txt"), "kept");
        using var ready = new ManualResetEventSlim(); using var removed = new ManualResetEventSlim();
        var cleanup = Task.Run(() => { Assert(ready.Wait(TimeSpan.FromSeconds(5)), "scanner did not reach queued directory"); Directory.Delete(child, true); removed.Set(); });
        string[] Enumerate(string path)
        {
            if (path == child) { ready.Set(); Assert(removed.Wait(TimeSpan.FromSeconds(5)), "concurrent cleanup did not finish"); }
            return Directory.GetFileSystemEntries(path);
        }
        if (running) Assert(service.ScanOutputFiles(root, running: true, enumerate: Enumerate).SequenceEqual(["kept.txt"]), "runtime scan lost persistent output");
        else
        {
            var rejected = false;
            try { service.ScanOutputFiles(root, enumerate: Enumerate); } catch (DirectoryNotFoundException) { rejected = true; }
            Assert(rejected, "strict final inventory tolerated a disappearing directory");
        }
        await cleanup;
    }
    // Missing persistent output is never made tolerant by the runtime option.
    var persistent = Path.Combine(work, "cleanup-persistent"); var model = Path.Combine(persistent, "model"); Directory.CreateDirectory(model);
    var missingRejected = false;
    try { service.ScanOutputFiles(persistent, running: true, enumerate: path => { if (path == model) Directory.Delete(model); return Directory.GetFileSystemEntries(path); }); }
    catch (DirectoryNotFoundException) { missingRejected = true; }
    Assert(missingRejected, "runtime scan ignored disappearing non-temporary output");
    // Quota enforcement remains active even inside the removable provider tree.
    var over = Path.Combine(work, "cleanup-quota"); Directory.CreateDirectory(Path.Combine(over, "_provider"));
    File.WriteAllText(Path.Combine(over, "_provider", "a"), "a"); File.WriteAllText(Path.Combine(over, "_provider", "b"), "b");
    using var bounded = new CladdingReviewService(settings with { MaximumFiles = 1 }); Reject(() => bounded.ScanOutputFiles(over, running: true));
    if (!OperatingSystem.IsWindows())
    {
        var linked = Path.Combine(work, "cleanup-symlink"); Directory.CreateDirectory(linked); Directory.CreateSymbolicLink(Path.Combine(linked, "_provider"), over);
        Reject(() => service.ScanOutputFiles(linked, running: true));
    }
});
CladdingReviewResult? single = null;
CladdingReviewResult? canopy = null;
if (python is not null)
{
    await Test("actual independent Skill subprocess one plate and replay", async () => { var r = Input(); single = await service.RunAsync(r); Assert(single.Manifest.Status == "REVIEW" && !single.Manifest.ManufacturingRelease && single.Manifest.ReleaseDecision == "NOT_RELEASED", "release improperly asserted"); Assert(single.Manifest.NestingStatus == "NOT_CONFIGURED", "unconfirmed stock fabricated"); Assert(single.Manifest.PreviewPlates[0].Box == CladdingReviewValidator.Box(r.Components[0]), "world geometry mismatch"); var again = await service.RunAsync(r); Assert(again.ManifestHash == single.ManifestHash && again.OutputDirectory == single.OutputDirectory, "replay regenerated output"); await RejectAsync(() => service.RunAsync(r with { Components = [r.Components[0] with { Grade = "Changed" }] })); });
    await Test("actual 56-part canopy XY/XZ all STEP drawings BOM same snapshot", async () => { using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(module, "examples", "canopy-reference-plates.json"))); var root = fixture.RootElement;
        foreach (var entry in new[] { (Path: "drawing", Hash: "drawingSha256"), (Path: "config", Hash: "configSha256") })
        {
            var source = root.GetProperty("source"); var relative = source.GetProperty(entry.Path).GetString()!;
            Assert(!Path.IsPathRooted(relative) && !relative.Split('/').Contains(".."), "unsafe fixture source path");
            var bytes = File.ReadAllBytes(Path.GetFullPath(Path.Combine(module, "..", relative)));
            Assert(Convert.ToHexString(SHA256.HashData(bytes)).Equals(source.GetProperty(entry.Hash).GetString(), StringComparison.OrdinalIgnoreCase), "original source drawing/config hash differs");
        }
        var r = Input() with { Components = root.GetProperty("components").Deserialize<PlateComponent[]>(StrictJson.Options)!, Evidence = root.GetProperty("evidence").Deserialize<CladdingSourceEvidence>(StrictJson.Options), Stock = null }; canopy = await service.RunAsync(r); Assert(canopy.Manifest.PreviewPlates.Length == 56, "canopy part omission"); Assert(r.Components.Count(x => x.Plane == "XY") == 42 && r.Components.Count(x => x.Plane == "XZ") == 14, "canopy orientation lost"); Assert(canopy.Manifest.Artifacts.Count(x => x.Kind == "model-step") == 56, "STEP output missing"); Assert(File.ReadAllText(Path.Combine(canopy.OutputDirectory, "drawings", "TP-01-01.svg")).Contains("2084.634"), "displayed SVG dimensions lost source precision"); Assert(File.ReadAllText(Path.Combine(canopy.OutputDirectory, "drawings", "TP-01-01.dxf")).Contains("2084.634"), "displayed DXF dimensions lost source precision"); using var bom = JsonDocument.Parse(File.ReadAllText(Path.Combine(canopy.OutputDirectory, "bom.json"))); Assert(bom.RootElement.GetProperty("rows").GetArrayLength() == 56, "BOM count differs"); var drawing = File.ReadAllText(Path.Combine(module, "..", "cad-fabrication-engineering-v3", "config", "canopy-reference-validation.yaml")); Assert(drawing.Length > 0 && r.Evidence!.SourceDrawingSha256 == root.GetProperty("source").GetProperty("drawingSha256").GetString(), "canopy source evidence lost"); });
    await Test("selected managed remeasurement through actual Skill", async () => { var r = Selected(); r = r with { Components = [r.Components[0] with { WidthMM = 805, Measurements = [new("widthMM", 800, 805, 805, "Explicit test measurement adoption")] }] }; var result = await service.RunAsync(r); Assert(result.Manifest.PreviewPlates[0].Box.Width == 805 && result.Request.Sources[0].BoxMM.Width == 800, "design/used source mismatch"); });
    await Test("trusted review gate rejects forged mixed and stale adoption", () => { var result = single ?? throw new Exception("prerequisite failed"); var p = Adoption(result); service.ValidateAdoption(p); Reject(() => service.ValidateAdoption(p with { Request = p.Request with { Provenance = p.Request.Provenance! with { ManifestHash = new string('F', 64) } } })); Reject(() => service.ValidateAdoption(p with { Request = p.Request with { Plates = [p.Request.Plates![0] with { Box = p.Request.Plates[0].Box with { Width = 999 } }] } })); var s = p.Snapshot with { Revision = p.Snapshot.Revision + 1 }; Reject(() => service.ValidateAdoption(p with { Snapshot = s, Request = p.Request with { Expected = PlanValidator.Expected(s) } })); return Task.CompletedTask; });
    await Test("changed missing extra duplicate and traversal artifacts rejected", () => { var r = single ?? throw new Exception("prerequisite failed"); var file = Path.Combine(r.OutputDirectory, r.Manifest.Artifacts.First(x => x.Kind == "model-step").Path); var original = File.ReadAllBytes(file); try { File.AppendAllText(file, "tampered"); Reject(() => service.Get(r.Manifest.JobId)); } finally { File.WriteAllBytes(file, original); } var moved = file + ".missing"; File.Move(file, moved); try { Reject(() => service.Get(r.Manifest.JobId)); } finally { File.Move(moved, file); } var extra = Path.Combine(r.OutputDirectory, "extra.txt"); File.WriteAllText(extra, "extra"); try { Reject(() => service.Get(r.Manifest.JobId)); } finally { File.Delete(extra); } var m = Path.Combine(r.OutputDirectory, "manifest.json"); var text = File.ReadAllText(m); try { File.WriteAllText(m, text.Replace("\"status\": \"REVIEW\"", "\"status\": \"REVIEW\", \"status\": \"REVIEW\"")); Reject(() => service.Get(r.Manifest.JobId)); var node = JsonNode.Parse(text)!; node["artifacts"]![0]!["path"] = "../escape"; File.WriteAllText(m, node.ToJsonString()); Reject(() => service.Get(r.Manifest.JobId)); } finally { File.WriteAllText(m, text); } Assert(service.Get(r.Manifest.JobId).ManifestHash == r.ManifestHash, "restored evidence invalid"); return Task.CompletedTask; });
    await Test("real Host HTTP skill review prepare and preapply revalidation", async () => { await HttpChecks(); });
    await Test("bounded timeout stdout files cancellation retain failed jobs", async () => { await ProcessFailures(); });
    await Test("source and adapter changes during generation prevent promotion", async () => { await SourceChanges(); });
    if (!OperatingSystem.IsWindows())
        await Test("symlink artifact state root and Skill root fail closed", () =>
        {
            var r = single ?? throw new Exception("prerequisite failed");
            var path = Path.Combine(r.OutputDirectory, "bom.csv"); var backup = path + ".backup"; File.Move(path, backup);
            try { File.CreateSymbolicLink(path, backup); Reject(() => service.Get(r.Manifest.JobId)); } finally { File.Delete(path); File.Move(backup, path); }
            var link = Path.Combine(work, "linked-state"); Directory.CreateSymbolicLink(link, settings.StateRoot);
            using var badState = new CladdingReviewService(settings with { StateRoot = link }); Reject(() => badState.Get(r.Manifest.JobId));
            var skillLink = Path.Combine(work, "linked-skill"); Directory.CreateSymbolicLink(skillLink, skill);
            using var badSkill = new CladdingReviewService(settings with { SkillRoot = skillLink }); Reject(() => badSkill.Get(r.Manifest.JobId));
            return Task.CompletedTask;
        });
    else results.Add(new { name = "symlink/reparse creation test", status = "NOT_RUN", reason = "Creating Windows symbolic links can require separate privilege; no security changes made." });
}
else results.Add(new { name = "real Skill subprocess, artifact readback and canopy regression", status = "NOT_RUN", reason = "No skillPython supplied; no real Skill or Rhino claim is made." });
var summary = new { schemaVersion = 1, timestamp = DateTimeOffset.UtcNow, environment = System.Runtime.InteropServices.RuntimeInformation.OSDescription, dotnet = Environment.Version.ToString(), runtimePython = python, realSkill = python is null ? "NOT_RUN" : failed == 0 ? "PASS" : "FAIL", liveWindowsRhino = "NOT_RUN", productionRelease = "NOT_RELEASED", passed = results.Count(x => JsonSerializer.Serialize(x).Contains("\"status\":\"PASS\"")), failed, singleJob = single?.Manifest.JobId, canopyJob = canopy?.Manifest.JobId, canopyOutputDirectory = canopy?.OutputDirectory, results };
File.WriteAllText(Path.Combine(evidence, "cladding-results.json"), JsonSerializer.Serialize(summary, Protocol.Json));
Console.WriteLine($"Cladding tests: {results.Count - failed} results, {failed} FAIL; real Skill {(python is null ? "NOT_RUN" : "executed")}; live Rhino NOT_RUN.");
return failed == 0 ? 0 : 1;

async Task Test(string name, Func<Task> action) { try { await action(); results.Add(new { name, status = "PASS" }); Console.WriteLine("PASS " + name); } catch (Exception e) { failed++; results.Add(new { name, status = "FAIL", error = e.Message }); Console.WriteLine("FAIL " + name + ": " + e.Message); } }
static void Assert(bool valid, string message) { if (!valid) throw new Exception(message); }
static void Reject(Action action) { try { action(); } catch (HarnessException) { return; } throw new Exception("expected rejection"); }
static void RejectJson(Action action) { try { action(); } catch (JsonException) { return; } throw new Exception("expected strict JSON rejection"); }
static async Task RejectAsync(Func<Task> action) { try { await action(); } catch (HarnessException) { return; } throw new Exception("expected rejection"); }
static CladdingReviewRequest Input()
{
    var s = new DocumentSnapshot(Guid.NewGuid(), Guid.NewGuid(), 0, "Millimeters", 0.01, [], []);
    return new(1, Guid.NewGuid(), PlanValidator.Expected(s), s, "explicit_design", [], [], [new("P-001", "测试板 P-001", new(23, -41, 67), 800, 300, 3, "Aluminum", "3003-H24", 2730, 1, [])], ["step", "drawings", "bom", "nesting"]);
}
static CladdingReviewRequest Selected()
{
    var r = Input(); var c = r.Components[0]; var e = new EntitySnapshot(Guid.NewGuid(), "SOURCE-001", "exact-test-fingerprint", "synthetic detached box fixture; not Rhino evidence", "{}", "Brep", true);
    var s = r.Snapshot with { Entities = [e] };
    return r with { Snapshot = s, Expected = PlanValidator.Expected(s), SourceMode = "selected_managed", SelectedEntityIds = [e.EntityId], Sources = [new(e.EntityId, e.Fingerprint, CladdingReviewValidator.Box(c))], Components = [c with { SourceEntityIds = [e.EntityId] }] };
}
static PrepareRequest Adoption(CladdingReviewResult r)
{
    var m = r.Manifest; var provenance = new PlateBatchProvenance(m.JobId, m.InputSnapshotHash, m.JobHash, r.ManifestHash, "cladding-delivery", m.SkillVersion, m.RuleVersion, m.SkillSourceHash);
    return new(new(1, Guid.NewGuid(), Guid.NewGuid(), "cladding.plates.add", r.Request.Expected, Plates: m.PreviewPlates.Select(x => new PlanarPlateSpec(x.EntityId, x.Box, x.Material)).ToArray(), Provenance: provenance), r.Request.Snapshot);
}
async Task HttpChecks()
{
    var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start(); var port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
    var nonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));
    var configuration = new DirectoryInfo(AppContext.BaseDirectory).Parent!.Name;
    var dll = Path.Combine(module, "src", "RhinoAi.Host", "bin", configuration, "net8.0", "RhinoAi.Host.dll");
    var start = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
    if (Path.GetFileNameWithoutExtension(Environment.ProcessPath) != "dotnet") start.FileName = Environment.GetEnvironmentVariable("DOTNET_HOST_PATH") ?? throw new Exception("DOTNET_HOST_PATH is required for apphost tests");
    start.ArgumentList.Add(dll);
    start.Environment["RHINOAI_SESSION_NONCE"] = nonce; start.Environment["RHINOAI_PORT"] = port.ToString(); start.Environment["RHINOAI_STATE_DIR"] = Path.Combine(work, "http-state"); start.Environment["RHINOAI_CLADDING_PYTHON"] = python; start.Environment["RHINOAI_CLADDING_SKILL_ROOT"] = skill; start.Environment["RHINOAI_CLADDING_ADAPTER_ROOT"] = adapter;
    using var host = Process.Start(start) ?? throw new Exception("Host did not start"); var stdout = host.StandardOutput.ReadToEndAsync(); var stderr = host.StandardError.ReadToEndAsync();
    try
    {
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}/"), Timeout = TimeSpan.FromSeconds(330) }; client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", nonce);
        var ready = false; for (var i = 0; i < 100; i++) { try { using var health = await client.GetAsync("health"); if (health.IsSuccessStatusCode) { ready = true; break; } } catch (HttpRequestException) { } if (host.HasExited) break; await Task.Delay(50); }
        Assert(ready, "Host did not become ready");
        var req = Input(); using var response = await client.PostAsJsonAsync("v2/cladding/review", req, Protocol.Json); Assert(response.IsSuccessStatusCode, "HTTP real review failed: " + await response.Content.ReadAsStringAsync()); var review = (await response.Content.ReadFromJsonAsync<CladdingReviewResult>(Protocol.Json))!;
        var prepare = Adoption(review); using var prepared = await client.PostAsJsonAsync("v1/prepare", prepare, Protocol.Json); Assert(prepared.IsSuccessStatusCode, "verified review prepare failed"); var plan = (await prepared.Content.ReadFromJsonAsync<ChangePlan>(Protocol.Json))!;
        var path = Path.Combine(review.OutputDirectory, "bom.csv"); File.AppendAllText(path, "tamper"); using var applying = await client.PostAsJsonAsync("v1/complete", new CompleteRequest(plan.Request.OperationId, plan.RequestHash, OperationState.Applying, null, null), Protocol.Json); Assert(!applying.IsSuccessStatusCode, "tampered outputs allowed Applying transition");
        using var stored = await client.GetAsync("v1/operations/" + plan.Request.OperationId); var op = (await stored.Content.ReadFromJsonAsync<OperationRecord>(Protocol.Json))!; Assert(op.State == OperationState.Prepared, "preapply rejection changed state or quarantined a mutation that never occurred");
        using var forged = await client.PostAsJsonAsync("v1/prepare", prepare with { Request = prepare.Request with { OperationId = Guid.NewGuid(), Provenance = prepare.Request.Provenance! with { JobId = Guid.NewGuid() } } }, Protocol.Json); Assert(!forged.IsSuccessStatusCode, "forged nonexistent review accepted");
    }
    finally { if (!host.HasExited) host.Kill(true); await host.WaitForExitAsync(); await stdout; await stderr; }
}
async Task ProcessFailures()
{
    foreach (var fault in new[] { "timeout", "stdout", "files", "partial", "cancel" })
    {
        var dir = Path.Combine(work, "fault-" + fault); Directory.CreateDirectory(dir); File.Copy(Path.Combine(adapter, "capabilities.json"), Path.Combine(dir, "capabilities.json")); File.Copy(Path.Combine(adapter, "request.schema.json"), Path.Combine(dir, "request.schema.json"));
        var body = fault switch { "stdout" => "print('x'*70000,flush=True)", "files" => "p.mkdir(); (p/'oversize').write_bytes(b'x'*2048); time.sleep(3)", "partial" => "p.mkdir(); (p/'partial').write_text('partial')", _ => "time.sleep(10)" };
        File.WriteAllText(Path.Combine(dir, "run.py"), "import sys,time,pathlib\np=pathlib.Path(sys.argv[sys.argv.index('--output')+1])\n" + body + "\n");
        using var other = new CladdingReviewService(settings with { AdapterRoot = dir, StateRoot = Path.Combine(work, "fault-state-" + fault), TimeoutSeconds = 1, MaximumArtifactBytes = fault == "files" ? 1024 : 33554432 });
        var r = Input(); using var cancellation = new CancellationTokenSource(); if (fault == "cancel") cancellation.CancelAfter(200);
        try { await other.RunAsync(r, cancellation.Token); throw new Exception("failed process falsely completed"); } catch (HarnessException) { } catch (OperationCanceledException) when (fault == "cancel") { }
        await RejectAsync(() => other.RunAsync(r)); Assert(!Directory.Exists(Path.Combine(work, "fault-state-" + fault, "completed", r.JobId.ToString("N"))), "partial job promoted");
    }
}

async Task SourceChanges()
{
    foreach (var kind in new[] { "adapter", "skill" })
    {
        var dir = Path.Combine(work, "mutation-" + kind); Directory.CreateDirectory(dir);
        foreach (var name in new[] { "run.py", "capabilities.json", "request.schema.json" }) File.Copy(Path.Combine(adapter, name), Path.Combine(dir, name));
        var script = Path.Combine(dir, "run.py");
        var text = File.ReadAllText(script);
        var signalLine = "manifest = run(args.skill_root, envelope, args.output)";
        Assert(text.Contains(signalLine), "mutation fixture signal insertion unavailable");
        text = text.Replace(signalLine, signalLine + "\n            (request_path.parent / 'ready.signal').write_text('ready')\n            __import__('time').sleep(2)");
        File.WriteAllText(script, text);
        var copiedSkill = skill;
        if (kind == "skill")
        {
            copiedSkill = Path.Combine(work, "mutation-skill-copy"); Directory.CreateDirectory(copiedSkill);
            foreach (var file in Directory.EnumerateFiles(skill, "*", SearchOption.AllDirectories))
            {
                var relative = Path.GetRelativePath(skill, file); var dest = Path.Combine(copiedSkill, relative); Directory.CreateDirectory(Path.GetDirectoryName(dest)!); File.Copy(file, dest);
            }
        }
        var state = Path.Combine(work, "mutation-state-" + kind);
        using var changed = new CladdingReviewService(settings with { AdapterRoot = dir, SkillRoot = copiedSkill, StateRoot = state, TimeoutSeconds = 30 });
        var r = Input(); var running = changed.RunAsync(r);
        var signaled = false;
        for (var i = 0; i < 200 && !running.IsCompleted; i++)
        {
            if (Directory.Exists(state) && Directory.EnumerateFiles(state, "ready.signal", SearchOption.AllDirectories).Any()) { signaled = true; break; }
            await Task.Delay(50);
        }
        if (!signaled) { await running; throw new Exception("real adapter did not reach postreadback mutation boundary"); }
        var changedFile = kind == "adapter" ? script : Path.Combine(copiedSkill, "src", "cladding_delivery", "bom.py");
        File.AppendAllText(changedFile, "\n# source change injected after verified artifact generation\n");
        await RejectAsync(() => running);
        Assert(!Directory.Exists(Path.Combine(state, "completed", r.JobId.ToString("N"))), "mixed rule/source revision was promoted");
        await RejectAsync(() => changed.RunAsync(r));
    }
}
