using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using RhinoAi.Contracts;
using RhinoAi.Core;
using RhinoAi.Host;

HostSettings settings;
HostJournal journal;
try
{
    if (args.Length != 0) throw new InvalidOperationException("Configure the host through its documented environment variables only.");
    settings = HostSettings.FromEnvironment();
    journal = new HostJournal(settings.StateDirectory);
}
catch (Exception)
{
    // Never log input bodies, credentials, paths, exception detail or stack traces.
    Console.Error.WriteLine("RhinoAi Host startup failed: check nonce, port, journal access/integrity, and exclusive ownership.");
    return 1;
}
using (journal)
{
    var builder = WebApplication.CreateSlimBuilder(new WebApplicationOptions { Args = [] });
    builder.Configuration.Sources.Clear();
    builder.Logging.ClearProviders();
    builder.WebHost.ConfigureKestrel(options =>
    {
        options.AddServerHeader = false;
        options.Limits.MaxRequestBodySize = HostSettings.MaximumBodyBytes;
        options.Limits.MaxRequestLineSize = 4096;
        options.Limits.MaxRequestHeadersTotalSize = 8192;
        options.Limits.KeepAliveTimeout = TimeSpan.FromSeconds(30);
        options.Limits.RequestHeadersTimeout = TimeSpan.FromSeconds(10);
        options.Listen(IPAddress.Loopback, settings.Port, listen => listen.Protocols = HttpProtocols.Http1);
    });
    var app = builder.Build();
    var nonceBytes = Encoding.ASCII.GetBytes(settings.Nonce);
    app.Use(async (context, next) =>
    {
        context.Response.Headers.CacheControl = "no-store";
        context.Response.Headers.XContentTypeOptions = "nosniff";
        try
        {
            var remote = context.Connection.RemoteIpAddress;
            if (remote is null || !IPAddress.IsLoopback(remote))
                throw new HostHttpException(403, "loopback_required", "Only the paired local plugin may connect.");
            if (context.Request.Headers.ContainsKey("Origin"))
                throw new HostHttpException(403, "browser_origin_rejected", "Browser-origin requests are not accepted.");
            var host = context.Request.Host;
            if (host.Port != settings.Port || !(string.Equals(host.Host, "localhost", StringComparison.OrdinalIgnoreCase) || host.Host == "127.0.0.1"))
                throw new HostHttpException(403, "host_rejected", "A matching loopback Host header is required.");
            var auth = context.Request.Headers.Authorization;
            if (auth.Count != 1 || auth[0] is not string header || !header.StartsWith("Bearer ", StringComparison.Ordinal))
                throw new HostHttpException(401, "unauthorized", "A valid paired-session bearer nonce is required.");
            var token = header[7..];
            if (token.Length != nonceBytes.Length || !token.All(char.IsAscii) || !CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(token), nonceBytes))
                throw new HostHttpException(401, "unauthorized", "A valid paired-session bearer nonce is required.");
            await next(context);
            if (context.Response.StatusCode is 404 or 405 && !context.Response.HasStarted)
                await WriteError(context, context.Response.StatusCode, "endpoint_not_found", "This endpoint or method is not supported.");
        }
        catch (HostHttpException error) { await WriteError(context, error.Status, error.Code, error.Message); }
        catch (HarnessException error) { await WriteError(context, 400, error.Code, error.Message); }
        catch (JsonException) { await WriteError(context, 400, "invalid_json", "Invalid JSON, missing or unknown fields, duplicate keys, or unsupported value types."); }
        catch (Microsoft.AspNetCore.Http.BadHttpRequestException error) { await WriteError(context, error.StatusCode == 413 ? 413 : 400, error.StatusCode == 413 ? "body_too_large" : "invalid_request", "The request body or HTTP framing is invalid or exceeds the limit."); }
        catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested) { }
        catch (Exception) { await WriteError(context, 500, "internal_error", "The operation failed. Inspect its stored status before retrying; no automatic replay is allowed."); }
    });
    app.MapGet("/health", () => { journal.CheckHealth(); return Results.Json(new { status = "ok", protocolVersion = Protocol.Version, mode = "deterministic-structured-tools", tools = new[] { "box.add", "object.translate", "checkpoint.restore" }, reviewStatus = "REVIEW" }, StrictJson.Options); });
    app.MapPost("/v1/prepare", async (HttpContext context) =>
    {
        var input = await StrictJson.ReadAsync<PrepareRequest>(context.Request, context.RequestAborted);
        ValidateRequiredPrepare(input);
        var plan = PlanValidator.Prepare(input);
        return Results.Json(journal.Prepare(plan), StrictJson.Options);
    });
    app.MapGet("/v1/operations/{id}", (string id) =>
    {
        if (!Guid.TryParseExact(id, "D", out var operationId) || operationId == Guid.Empty)
            throw new HostHttpException(400, "invalid_id", "Use a nonempty operation UUID in canonical hyphenated format.");
        return Results.Json(journal.Get(operationId), StrictJson.Options);
    });
    app.MapPost("/v1/complete", async (HttpContext context) =>
    {
        var input = await StrictJson.ReadAsync<CompleteRequest>(context.Request, context.RequestAborted);
        if (input.OperationId == Guid.Empty || string.IsNullOrWhiteSpace(input.RequestHash))
            throw new HostHttpException(400, "invalid_completion", "Operation ID and request hash are required.");
        return Results.Json(journal.Complete(input), StrictJson.Options);
    });
    try
    {
        await app.StartAsync();
        Console.WriteLine($"RhinoAi Host ready at http://127.0.0.1:{settings.Port}; protocol {Protocol.Version}; REVIEW.");
        await app.WaitForShutdownAsync();
    }
    catch (Exception error) when (error is IOException or InvalidOperationException)
    {
        Console.Error.WriteLine("RhinoAi Host could not start or continue its loopback listener.");
        return 1;
    }
}
return 0;

static void ValidateRequiredPrepare(PrepareRequest input)
{
    if (input.Request is null || input.Snapshot is null || input.Request.Expected is null || input.Request.ToolId is null || input.Snapshot.Entities is null || input.Snapshot.Entities.Any(x => x is null))
        throw new HostHttpException(400, "required_field", "Request, expected context, snapshot and non-null entity entries are required.");
    if (input.RestoreTarget is not null && (input.RestoreTarget.Snapshot is null || input.RestoreTarget.Snapshot.Entities is null || input.RestoreTarget.Snapshot.Entities.Any(x => x is null)))
        throw new HostHttpException(400, "required_field", "The restore target must contain a complete snapshot.");
}
static async Task WriteError(HttpContext context, int status, string code, string message)
{
    if (context.Response.HasStarted) { context.Abort(); return; }
    context.Response.StatusCode = status;
    if (status == 401) context.Response.Headers.WWWAuthenticate = "Bearer";
    await context.Response.WriteAsJsonAsync(new ApiError(code, message), StrictJson.Options, context.RequestAborted);
}
