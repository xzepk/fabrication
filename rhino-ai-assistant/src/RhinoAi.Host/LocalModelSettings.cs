using System.Text.RegularExpressions;

namespace RhinoAi.Host;

/// <summary>No credentials or remote providers. Endpoint is the literal IPv4-loopback Chat Completions route.</summary>
public sealed record LocalModelSettings(Uri? Endpoint, string? Model, string Status, TimeSpan Timeout)
{
    public const int MaximumPromptChars = 4096;
    public const int MaximumSelectedObjects = 16;
    public const int MaximumContextObjects = 64;
    public const int MaximumInputTextBytes = 16_384;
    public const int MaximumRequestBytes = 32_768;
    public const int MaximumResponseBytes = 65_536;
    public const int MaximumOutputTokens = 1024;
    public static readonly TimeSpan MaximumTimeout = TimeSpan.FromSeconds(20);

    public static LocalModelSettings FromEnvironment() => Parse(
        Environment.GetEnvironmentVariable("RHINOAI_MODEL_ENDPOINT"),
        Environment.GetEnvironmentVariable("RHINOAI_MODEL"));

    public static LocalModelSettings Parse(string? endpoint, string? model)
    {
        if (string.IsNullOrWhiteSpace(endpoint) && string.IsNullOrWhiteSpace(model)) return new(null, null, "NOT_CONFIGURED", MaximumTimeout);
        // Check raw authority as well as Uri: .NET normalizes alternate numeric IP spellings to 127.0.0.1.
        if (endpoint is null || !Regex.IsMatch(endpoint, @"\Ahttp://127\.0\.0\.1:[1-9][0-9]{3,4}/v1/chat/completions\z", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100)) ||
            !Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || uri.Port is < 1024 or > 65535 ||
            model is null || !Regex.IsMatch(model, @"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\z", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100)))
            return new(null, null, "INVALID_CONFIGURATION", MaximumTimeout);
        return new(uri, model, "READY", MaximumTimeout);
    }
}
