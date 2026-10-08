using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using RhinoAi.Contracts;

namespace RhinoAi.Plugin;

/// <summary>Explicit literal-loopback endpoint, authenticated on every request. Nonce is memory/environment only.</summary>
public sealed class AgentHostClient : IDisposable
{
    private readonly HttpClient _http;
    private Process? _ownedProcess;
    public Uri Endpoint { get; }
    private AgentHostClient(Uri endpoint, string nonce)
    {
        if (endpoint.Scheme != "http" || endpoint.Host != "127.0.0.1" || endpoint.AbsolutePath != "/" || !string.IsNullOrEmpty(endpoint.Query) || !string.IsNullOrEmpty(endpoint.UserInfo) || !string.IsNullOrEmpty(endpoint.Fragment))
            throw new HarnessException("host-endpoint", "Use an explicit http://127.0.0.1:port endpoint without credentials, query or path.");
        if (nonce.Length < 32 || nonce.Any(x => x < 33 || x > 126)) throw new HarnessException("host-nonce", "Host nonce must contain at least 32 printable ASCII characters.");
        Endpoint = endpoint;
        _http = new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = false, UseProxy = false }) { BaseAddress = endpoint, Timeout = Timeout.InfiniteTimeSpan };
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", nonce);
    }
    public static async Task<AgentHostClient> AttachAsync(Uri endpoint, string nonce, CancellationToken ct = default)
    {
        var client = new AgentHostClient(endpoint, nonce);
        try { await client.HealthAsync(ct); return client; }
        catch { client.Dispose(); throw; }
    }
    public static async Task<AgentHostClient> StartAsync(string executablePath, int port, string stateDirectory, CancellationToken ct = default)
    {
        executablePath = Path.GetFullPath(executablePath);
        if (!File.Exists(executablePath) || !string.Equals(Path.GetExtension(executablePath), ".exe", StringComparison.OrdinalIgnoreCase))
            throw new HarnessException("host-path", "Select the separately built Windows RhinoAi.Host.exe executable.");
        if (port is < 1024 or > 65535) throw new HarnessException("host-port", "Use a port between 1024 and 65535.");
        var nonce = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var client = new AgentHostClient(new Uri($"http://127.0.0.1:{port}/"), nonce);
        var start = new ProcessStartInfo(executablePath) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(executablePath)! };
        start.Environment["RHINOAI_SESSION_NONCE"] = nonce;
        start.Environment["RHINOAI_PORT"] = port.ToString(System.Globalization.CultureInfo.InvariantCulture);
        start.Environment["RHINOAI_STATE_DIR"] = Path.GetFullPath(stateDirectory);
        try
        {
            client._ownedProcess = Process.Start(start) ?? throw new HarnessException("host-start", "Host did not start.");
            for (var attempt = 0; attempt < 60; attempt++)
            {
                ct.ThrowIfCancellationRequested();
                if (client._ownedProcess.HasExited) throw new HarnessException("host-exited", "Host exited before becoming ready. Check the configured path, port and journal-directory ownership.");
                try { await client.HealthAsync(ct); return client; }
                catch (HttpRequestException) { }
                await Task.Delay(200, ct);
            }
            throw new HarnessException("host-timeout", "Host did not become ready on the selected loopback port.");
        }
        catch { client.Dispose(); throw; }
        finally { start.Environment.Remove("RHINOAI_SESSION_NONCE"); }
    }
    public async Task HealthAsync(CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15)); ct = deadline.Token;
        using var response = await _http.GetAsync("health", ct);
        await RequireSuccess(response, ct);
    }
    public async Task<PlannerResponse> PlanAsync(PlannerRequest request, CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(30)); ct = deadline.Token;
        using var response = await _http.PostAsJsonAsync("v2/plan", request, Protocol.Json, ct);
        await RequireSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<PlannerResponse>(Protocol.Json, ct) ?? throw new HarnessException("host-response", "Host returned no planner result.");
    }
    public async Task<CladdingReviewResult> ReviewCladdingAsync(CladdingReviewRequest request, CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(330)); ct = deadline.Token;
        using var response = await _http.PostAsJsonAsync("v2/cladding/review", request, Protocol.Json, ct);
        await RequireSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<CladdingReviewResult>(Protocol.Json, ct) ?? throw new HarnessException("host-response", "Host returned no cladding review.");
    }
    public async Task<ChangePlan> PrepareAsync(PrepareRequest request, CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15)); ct = deadline.Token;
        using var response = await _http.PostAsJsonAsync("v1/prepare", request, Protocol.Json, ct);
        await RequireSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<ChangePlan>(Protocol.Json, ct) ?? throw new HarnessException("host-response", "Host returned no plan.");
    }
    public async Task<OperationRecord?> GetAsync(Guid id, CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15)); ct = deadline.Token;
        using var response = await _http.GetAsync($"v1/operations/{id:D}", ct);
        if (response.StatusCode == HttpStatusCode.NotFound) return null;
        await RequireSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<OperationRecord>(Protocol.Json, ct);
    }
    public async Task<OperationRecord> CompleteAsync(OperationRecord record, CancellationToken ct = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15)); ct = deadline.Token;
        var body = new CompleteRequest(record.OperationId, record.RequestHash, record.State, record.Outcome, record.Error);
        using var response = await _http.PostAsJsonAsync("v1/complete", body, Protocol.Json, ct);
        await RequireSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<OperationRecord>(Protocol.Json, ct) ?? throw new HarnessException("host-response", "Host returned no acknowledged operation.");
    }
    private static async Task RequireSuccess(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        ApiError? error = null;
        try { error = await response.Content.ReadFromJsonAsync<ApiError>(Protocol.Json, ct); } catch (JsonException) { }
        throw new HarnessException(error?.Code ?? "host-http", error?.Message ?? $"Host returned HTTP {(int)response.StatusCode}. No automatic replay was attempted.");
    }
    public void Dispose()
    {
        _http.Dispose();
        if (_ownedProcess is not null)
        {
            try { if (!_ownedProcess.HasExited) _ownedProcess.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
            _ownedProcess.Dispose(); _ownedProcess = null;
        }
    }
}
