namespace RhinoAi.Host;

/// <summary>Trusted single-machine administrator configuration. No request or model response supplies paths.</summary>
public sealed record CladdingAdapterSettings(string? PythonPath, string? SkillRoot, string AdapterRoot, string StateRoot,
    int TimeoutSeconds = 300, int MaximumOutputBytes = 65536, int MaximumFiles = 1000,
    long MaximumArtifactBytes = 33554432, long MaximumTotalBytes = 134217728)
{
    public bool IsConfigured => PythonPath is not null && SkillRoot is not null;
    public static CladdingAdapterSettings FromEnvironment(string stateDirectory)
    {
        var python = Environment.GetEnvironmentVariable("RHINOAI_CLADDING_PYTHON");
        var skill = Environment.GetEnvironmentVariable("RHINOAI_CLADDING_SKILL_ROOT");
        var adapter = Environment.GetEnvironmentVariable("RHINOAI_CLADDING_ADAPTER_ROOT") ?? Path.Combine(AppContext.BaseDirectory, "adapters", "cladding");
        if ((python is null) != (skill is null)) throw new InvalidOperationException("Both cladding interpreter and Skill root must be configured together.");
        foreach (var value in new[] { python, skill, adapter, stateDirectory }.Where(x => x is not null))
            if (!Path.IsPathFullyQualified(value!)) throw new InvalidOperationException("Cladding configuration paths must be absolute.");
        return new(python, skill, adapter, Path.Combine(stateDirectory, "cladding-reviews"));
    }
}
