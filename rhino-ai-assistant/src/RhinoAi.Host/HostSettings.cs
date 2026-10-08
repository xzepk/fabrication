using System.Globalization;

namespace RhinoAi.Host;

public sealed record HostSettings(int Port, string Nonce, string StateDirectory)
{
    public const int MaximumBodyBytes = 1_048_576;
    public static HostSettings FromEnvironment()
    {
        var nonce = Environment.GetEnvironmentVariable("RHINOAI_SESSION_NONCE");
        if (nonce is null || nonce.Length is < 32 or > 256 || nonce.Any(c => !(char.IsAsciiLetterOrDigit(c) || c is '-' or '_')))
            throw new InvalidOperationException("RHINOAI_SESSION_NONCE must be a random base64url nonce of 32 to 256 characters.");
        // Retain the nonce only in this process's memory, not its inherited environment.
        Environment.SetEnvironmentVariable("RHINOAI_SESSION_NONCE", null);
        var text = Environment.GetEnvironmentVariable("RHINOAI_PORT") ?? "47831";
        if (!int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var port) || port is < 1024 or > 65535)
            throw new InvalidOperationException("RHINOAI_PORT must be an integer from 1024 to 65535.");
        var directory = Environment.GetEnvironmentVariable("RHINOAI_STATE_DIR") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RhinoAi", "HostJournal");
        if (!Path.IsPathFullyQualified(directory))
            throw new InvalidOperationException("RHINOAI_STATE_DIR must be an absolute path.");
        return new HostSettings(port, nonce, Path.GetFullPath(directory));
    }
}
