using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RhinoAi.Contracts;
using RhinoAi.Core;

[assembly: InternalsVisibleTo("RhinoAi.Cladding.Tests")]

namespace RhinoAi.Host;

/// <summary>A fixed, bounded, isolated local subprocess. Immutable job claims prevent automatic crash/failed-run replay.
/// Successful outputs are verified in staging and atomically promoted; no LLM-provided executable or output path exists.</summary>
public sealed class CladdingReviewService(CladdingAdapterSettings settings) : IDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private const string Policy = "rhino-cladding-planar-v1:";
    private sealed record Receipt(Guid JobId, string RequestHash, string JobHash, string ManifestHash);
    private string Completed(Guid id) => Path.Combine(settings.StateRoot, "completed", id.ToString("N"));
    public void Dispose() => _gate.Dispose();

    public async Task<CladdingReviewResult> RunAsync(CladdingReviewRequest request, CancellationToken cancellationToken = default)
    {
        CladdingReviewValidator.Validate(request);
        await _gate.WaitAsync(cancellationToken);
        try
        {
            RequireConfigured();
            var envelope = Envelope(request);
            if (JsonSerializer.SerializeToUtf8Bytes(envelope, Protocol.Json).Length > HostSettings.MaximumBodyBytes) throw Error("cladding-request-limit", "The complete immutable request exceeds the 1 MiB limit.");
            EnsureRoot();
            var complete = Completed(request.JobId);
            if (Directory.Exists(complete))
            {
                var prior = ReadCompleted(request.JobId);
                if (prior.Manifest.RequestHash != envelope.RequestHash || prior.Manifest.JobHash != envelope.JobHash)
                    throw Error("cladding-replay-conflict", "This job UUID is already bound to different input or rule/Skill versions; use a new job UUID.");
                return prior;
            }
            var claim = Path.Combine(settings.StateRoot, "claims", request.JobId.ToString("N") + ".json");
            SafeAncestors(claim);
            if (File.Exists(claim)) throw Error("cladding-incomplete", "This job already started but has no verified committed output. Its evidence is preserved; use a new job UUID after reviewing the failure.");
            WriteNew(claim, envelope);
            var stage = Path.Combine(settings.StateRoot, "staging", request.JobId.ToString("N") + "-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            var input = Path.Combine(stage, "request.json");
            var output = Path.Combine(stage, "output");
            WriteNew(input, envelope);
            try
            {
                await RunProcess(input, output, cancellationToken);
                // Code/Skill changes during generation invalidate the entire run.
                if (Envelope(request) != envelope) throw Error("cladding-version-changed", "Adapter or Skill source changed during generation. Partial evidence was retained.");
                var manifest = ReadOutput(output, envelope);
                var manifestHash = FileHash(Path.Combine(output, "manifest.json"));
                WriteNew(Path.Combine(stage, "receipt.json"), new Receipt(request.JobId, envelope.RequestHash, envelope.JobHash, manifestHash));
                cancellationToken.ThrowIfCancellationRequested();
                SafeAncestors(stage); SafeAncestors(complete);
                Directory.Move(stage, complete); // same-volume atomic directory promotion; never overwrite
                return ReadCompleted(request.JobId);
            }
            catch
            {
                // Never erase/repurpose a failed staging run, or silently retry after an uncertain process result.
                throw;
            }
        }
        finally { _gate.Release(); }
    }

    public CladdingReviewResult Get(Guid jobId)
    {
        if (jobId == Guid.Empty) throw Error("invalid-job", "A nonempty review job UUID is required.");
        RequireConfigured();
        return ReadCompleted(jobId);
    }

    public void ValidateAdoption(PrepareRequest input) => ValidatePreview(input.Request, input.Snapshot);
    public void ValidateForApply(ChangePlan plan) => ValidatePreview(plan.Request, plan.Before);
    public void ValidatePreview(ToolRequest request, DocumentSnapshot snapshot)
    {
        if (request.ToolId != "cladding.plates.add") return;
        PlanValidator.ValidateSnapshot(snapshot); PlanValidator.Match(request.Expected, snapshot);
        var p = request.Provenance ?? throw Error("cladding-provenance", "A verified immutable cladding job is required.");
        var review = Get(p.JobId);
        var m = review.Manifest;
        var expected = new PlateBatchProvenance(m.JobId, m.InputSnapshotHash, m.JobHash, review.ManifestHash, "cladding-delivery", m.SkillVersion, m.RuleVersion, m.SkillSourceHash);
        if (p != expected || snapshot.SnapshotHash != m.InputSnapshotHash || review.Request.Expected != request.Expected)
            throw Error("cladding-stale-review", "The job, source snapshot or rule/Skill provenance differs from the reviewed output. Prepare a new review.");
        var plates = request.Plates;
        if (plates is null || plates.Length != m.PreviewPlates.Length || plates.Where((x, i) => x is null || x.EntityId != m.PreviewPlates[i].EntityId || x.Box != m.PreviewPlates[i].Box || x.Material != m.PreviewPlates[i].Material).Any())
            throw Error("cladding-mixed-review", "Adoption must use every exact plate from one immutable review in its original order.");
    }

    private CladdingReviewResult ReadCompleted(Guid jobId)
    {
        var complete = Completed(jobId);
        if (!Directory.Exists(complete)) throw Error("cladding-not-found", "No complete verified review exists for this job UUID.");
        SafeAncestors(complete);
        var entries = Directory.EnumerateFileSystemEntries(complete).Select(Path.GetFileName).ToHashSet(StringComparer.Ordinal);
        if (!entries.SetEquals(["request.json", "receipt.json", "output"])) throw Error("cladding-integrity", "Unexpected or missing files in the immutable job directory.");
        var envelope = Read<CladdingAdapterEnvelope>(Path.Combine(complete, "request.json"), HostSettings.MaximumBodyBytes);
        CladdingReviewValidator.Validate(envelope.Request);
        if (envelope.Request.JobId != jobId || Envelope(envelope.Request) != envelope)
            throw Error("cladding-version-changed", "Stored input or the configured rule/Skill source differs from this review. Generate a new job.");
        var claim = Read<CladdingAdapterEnvelope>(Path.Combine(settings.StateRoot, "claims", jobId.ToString("N") + ".json"), HostSettings.MaximumBodyBytes);
        if (Protocol.Hash(claim) != Protocol.Hash(envelope)) throw Error("cladding-integrity", "Job identity reservation differs from the committed request.");
        var output = Path.Combine(complete, "output");
        var manifest = ReadOutput(output, envelope);
        var hash = FileHash(Path.Combine(output, "manifest.json"));
        var receipt = Read<Receipt>(Path.Combine(complete, "receipt.json"), 65536);
        if (receipt != new Receipt(jobId, envelope.RequestHash, envelope.JobHash, hash))
            throw Error("cladding-integrity", "Committed review receipt does not match current output bytes.");
        return new(manifest, hash, envelope.Request, output);
    }

    private CladdingReviewManifest ReadOutput(string output, CladdingAdapterEnvelope envelope)
    {
        SafeAncestors(output);
        var manifest = Read<CladdingReviewManifest>(Path.Combine(output, "manifest.json"), HostSettings.MaximumBodyBytes);
        if (manifest.ProtocolVersion != Protocol.Version || manifest.JobId != envelope.Request.JobId || manifest.RequestHash != envelope.RequestHash || manifest.InputSnapshotHash != envelope.InputSnapshotHash || manifest.JobHash != envelope.JobHash || manifest.RuleVersion != envelope.RuleVersion || manifest.SkillVersion != envelope.SkillVersion || manifest.SkillSourceHash != envelope.SkillSourceHash || manifest.Status != "REVIEW" || manifest.ManufacturingRelease || manifest.ReleaseDecision != "NOT_RELEASED")
            throw Error("cladding-mixed-review", "Output manifest is missing immutable bindings or improperly claims production release.");
        var expectedPlates = envelope.Request.Components.Select(x => new CladdingPreviewPlate(x.EntityId, CladdingReviewValidator.Box(x), x.Material)).ToArray();
        if (manifest.PreviewPlates is null || !manifest.PreviewPlates.SequenceEqual(expectedPlates)) throw Error("cladding-geometry-mismatch", "Preview geometry differs from the exact requested plates.");
        if (manifest.NestingStatus is not ("REVIEW" or "NOT_CONFIGURED" or "BLOCKED") || envelope.Request.Stock is null && manifest.NestingStatus != "NOT_CONFIGURED" || manifest.Warnings is null)
            throw Error("cladding-nesting", "Nesting status must explicitly preserve missing stock and review-only process conditions.");
        if (manifest.Artifacts is null || manifest.Artifacts.Length is < 8 || manifest.Artifacts.Length >= settings.MaximumFiles || manifest.Artifacts.Any(x => x is null))
            throw Error("cladding-artifacts", "The complete bounded review artifact list is required.");
        var expectedFiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "manifest.json" };
        long total = 0;
        foreach (var artifact in manifest.Artifacts)
        {
            if (!SafeRelative(artifact.Path) || !expectedFiles.Add(artifact.Path) || artifact.Bytes is <= 0 || artifact.Bytes > settings.MaximumArtifactBytes || !Digest(artifact.Sha256))
                throw Error("cladding-artifacts", "Unsafe, duplicate, empty or oversized review artifact entry.");
            var path = Path.Combine(output, artifact.Path.Replace('/', Path.DirectorySeparatorChar));
            SafeAncestors(path);
            var info = new FileInfo(path);
            if (!info.Exists || info.Length != artifact.Bytes || !SameHash(FileHash(path), artifact.Sha256)) throw Error("cladding-integrity", "A review artifact is missing or its bytes changed.");
            total = checked(total + info.Length);
            if (total > settings.MaximumTotalBytes) throw Error("cladding-output-limit", "The review artifact bundle exceeds the configured size limit.");
        }
        var actual = ScanOutputFiles(output);
        if (actual.Length != actual.ToHashSet(StringComparer.OrdinalIgnoreCase).Count || !actual.ToHashSet(StringComparer.OrdinalIgnoreCase).SetEquals(expectedFiles)) throw Error("cladding-integrity", "Manifest hash coverage differs from the complete output file set.");
        var expectedDirectories = new HashSet<string>(StringComparer.Ordinal);
        foreach (var relative in expectedFiles)
        {
            var parts = relative.Split('/');
            for (var i = 1; i < parts.Length; i++) expectedDirectories.Add(string.Join('/', parts.Take(i)));
        }
        var actualDirectories = Directory.EnumerateDirectories(output, "*", SearchOption.AllDirectories).Select(x => Path.GetRelativePath(output, x).Replace('\\', '/')).ToHashSet(StringComparer.Ordinal);
        if (!actualDirectories.SetEquals(expectedDirectories)) throw Error("cladding-integrity", "Unexpected or missing output directories.");
        foreach (var name in new[] { "input_snapshot.json", "provenance.json", "bom.json", "bom.csv", "nesting.json", "label_map.json", "readback.json", "assembly-review.svg" })
            if (!expectedFiles.Contains(name)) throw Error("cladding-artifacts", "Required same-snapshot model/drawing/BOM/nesting metadata is missing.");
        foreach (var plate in expectedPlates)
            foreach (var kind in new[] { "model-step", "blank-dxf", "drawing-dxf", "drawing-svg" })
                if (manifest.Artifacts.Count(a => a.EntityId == plate.EntityId && a.Kind == kind) != 1) throw Error("cladding-artifacts", "Each plate needs one verified STEP, manufacturing blank, review DXF and review SVG.");
        var captured = Read<CladdingAdapterEnvelope>(Path.Combine(output, "input_snapshot.json"), HostSettings.MaximumBodyBytes);
        if (Protocol.Hash(captured) != Protocol.Hash(envelope)) throw Error("cladding-mixed-review", "Artifacts capture a different input snapshot.");
        CheckMetadataBindings(Path.Combine(output, "provenance.json"), envelope);
        CheckMetadataBindings(Path.Combine(output, "readback.json"), envelope);
        return manifest;
    }

    private void CheckMetadataBindings(string path, CladdingAdapterEnvelope envelope)
    {
        using var doc = JsonDocument.Parse(ReadBytes(path, HostSettings.MaximumBodyBytes));
        var root = doc.RootElement;
        StrictJson.CheckNoDuplicateProperties(root);
        foreach (var pair in new Dictionary<string, string> { ["requestHash"] = envelope.RequestHash, ["inputSnapshotHash"] = envelope.InputSnapshotHash, ["jobHash"] = envelope.JobHash, ["ruleVersion"] = envelope.RuleVersion, ["skillVersion"] = envelope.SkillVersion, ["skillSourceHash"] = envelope.SkillSourceHash })
            if (!root.TryGetProperty(pair.Key, out var value) || value.ValueKind != JsonValueKind.String || value.GetString() != pair.Value)
                throw Error("cladding-mixed-review", "Output metadata does not bind the same input and rule/Skill revision.");
    }

    public object Capabilities()
    {
        var version = RuleVersion();
        using var json = JsonDocument.Parse(ReadBytes(Path.Combine(settings.AdapterRoot, "capabilities.json"), 65536));
        StrictJson.CheckNoDuplicateProperties(json.RootElement);
        var root = json.RootElement;
        if (root.GetProperty("skillId").GetString() != "cladding-delivery" || root.GetProperty("manufacturingRelease").GetBoolean() || root.GetProperty("releaseDecision").GetString() != "NOT_RELEASED")
            throw Error("cladding-capability", "The packaged Skill capability manifest is invalid.");
        return new { configured = settings.IsConfigured, configurationStatus = settings.IsConfigured ? "CONFIGURED" : "NOT_CONFIGURED", ruleVersion = version, capability = root.Clone() };
    }
    private string RuleVersion()
    {
        var lines = new StringBuilder();
        foreach (var name in new[] { "capabilities.json", "request.schema.json", "run.py" })
            lines.Append(name).Append(' ').Append(FileHash(Path.Combine(settings.AdapterRoot, name))).Append('\n');
        return Policy + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(lines.ToString())));
    }

    private CladdingAdapterEnvelope Envelope(CladdingReviewRequest request)
    {
        RequireConfigured();
        var script = Path.Combine(settings.AdapterRoot, "run.py");
        SafeAncestors(script); SafeAncestors(settings.SkillRoot!);
        var rule = RuleVersion();
        var skillManifest = Path.Combine(settings.SkillRoot!, "MANIFEST.sha256");
        var skillHash = FileHash(skillManifest);
        VerifySkillManifest(skillManifest);
        using var source = JsonDocument.Parse(ReadBytes(Path.Combine(settings.SkillRoot!, "SOURCE_REVISION.json"), 65536));
        var version = source.RootElement.GetProperty("version").GetString() ?? throw Error("cladding-skill-version", "Skill version is missing.");
        var requestHash = Protocol.Hash(request);
        var jobHash = Protocol.Hash(new { RequestHash = requestHash, InputSnapshotHash = request.Snapshot.SnapshotHash, RuleVersion = rule, SkillVersion = version, SkillSourceHash = skillHash });
        return new(requestHash, request.Snapshot.SnapshotHash, jobHash, rule, version, skillHash, request);
    }

    private void VerifySkillManifest(string manifest)
    {
        var lines = Encoding.UTF8.GetString(ReadBytes(manifest, 1048576)).Split('\n', StringSplitOptions.RemoveEmptyEntries);
        if (lines.Length is < 1 or > 5000) throw Error("cladding-skill-integrity", "Skill manifest is missing or exceeds bounds.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in lines)
        {
            var entry = line.TrimEnd('\r');
            if (entry.Length < 67 || entry[64..66] != "  " || !Digest(entry[..64]) || !SafeRelative(entry[66..]) || !names.Add(entry[66..]))
                throw Error("cladding-skill-integrity", "Skill manifest entry is invalid.");
            var path = Path.Combine(settings.SkillRoot!, entry[66..].Replace('/', Path.DirectorySeparatorChar));
            SafeAncestors(path);
            if (!SameHash(FileHash(path), entry[..64])) throw Error("cladding-skill-integrity", "Independent Skill source differs from its versioned source manifest.");
        }
        // Unlisted executable source cannot shadow a trusted package module.
        foreach (var path in Directory.EnumerateFiles(Path.Combine(settings.SkillRoot!, "src"), "*", SearchOption.AllDirectories))
            if (!names.Contains(Path.GetRelativePath(settings.SkillRoot!, path).Replace('\\', '/'))) throw Error("cladding-skill-integrity", "Unlisted Python source was found in the independent Skill.");
    }

    private async Task RunProcess(string input, string output, CancellationToken caller)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(settings.TimeoutSeconds));
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(caller, timeout.Token);
        var start = new ProcessStartInfo(settings.PythonPath!) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(input)! };
        start.ArgumentList.Add("-I"); start.ArgumentList.Add("-B"); start.ArgumentList.Add("-X"); start.ArgumentList.Add("pycache_prefix=" + Path.Combine(Path.GetDirectoryName(input)!, "python-cache")); start.ArgumentList.Add(Path.Combine(settings.AdapterRoot, "run.py"));
        start.ArgumentList.Add("--skill-root"); start.ArgumentList.Add(settings.SkillRoot!);
        start.ArgumentList.Add("--request"); start.ArgumentList.Add(input);
        start.ArgumentList.Add("--output"); start.ArgumentList.Add(output);
        var allowed = new[] { "SystemRoot", "WINDIR", "TEMP", "TMP" }.Select(k => (Key: k, Value: Environment.GetEnvironmentVariable(k))).Where(x => x.Value is not null).ToArray();
        start.Environment.Clear();
        foreach (var entry in allowed) start.Environment[entry.Key] = entry.Value;
        start.Environment["PYTHONNOUSERSITE"] = "1"; start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        using var process = new Process { StartInfo = start };
        try
        {
            if (!process.Start()) throw Error("cladding-start", "The configured local Skill process could not start.");
            process.StandardInput.Close();
            using var registration = linked.Token.Register(() => { try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { } });
            var stdout = DrainBounded(process.StandardOutput, process, linked.Token);
            var stderr = DrainBounded(process.StandardError, process, linked.Token);
            await Task.WhenAll(process.WaitForExitAsync(linked.Token), stdout, stderr, MonitorOutputs(output, process, linked.Token));
            if (process.ExitCode != 0) throw Error("cladding-process-failed", "The independent Skill process rejected the input or failed. Partial evidence is retained; no output was committed.");
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested && !caller.IsCancellationRequested)
        { throw Error("cladding-timeout", "The bounded local Skill process exceeded its deadline. No output was committed."); }
        finally
        {
            try { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(); } } catch (InvalidOperationException) { }
        }
    }

    private async Task MonitorOutputs(string output, Process process, CancellationToken cancellationToken)
    {
        while (!process.HasExited)
        {
            if (Directory.Exists(output))
            {
                try
                {
                    long total = 0;
                    foreach (var relative in ScanOutputFiles(output, running: true))
                    {
                        var file = new FileInfo(Path.Combine(output, relative.Replace('/', Path.DirectorySeparatorChar)));
                        if (!file.Exists) continue; // Provider-owned temporary artifact removed between observations.
                        var length = file.Length;
                        total += length;
                        if (length > settings.MaximumArtifactBytes || total > settings.MaximumTotalBytes)
                            throw Error("cladding-output-limit", "The running Skill exceeded its file size limits; no output was committed.");
                    }
                }
                catch (HarnessException)
                {
                    try { process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
                    throw;
                }
            }
            await Task.Delay(100, cancellationToken);
        }
    }

    private async Task DrainBounded(StreamReader stream, Process process, CancellationToken cancellationToken)
    {
        var buffer = new char[2048];
        long bytes = 0;
        while (true)
        {
            var count = await stream.ReadAsync(buffer.AsMemory(), cancellationToken);
            if (count == 0) return;
            bytes += Encoding.UTF8.GetByteCount(buffer, 0, count);
            if (bytes > settings.MaximumOutputBytes)
            {
                try { process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
                throw Error("cladding-log-limit", "The Skill process exceeded its bounded output limit. No output was committed.");
            }
        }
    }
    private void RequireConfigured()
    {
        if (!settings.IsConfigured) throw Error("cladding-not-configured", "Configure the trusted local Python executable and independent cladding Skill root before running a review.");
        if (!Path.IsPathFullyQualified(settings.PythonPath!) || !File.Exists(settings.PythonPath) || !Path.IsPathFullyQualified(settings.SkillRoot!) || !Path.IsPathFullyQualified(settings.AdapterRoot) || !Path.IsPathFullyQualified(settings.StateRoot) || settings.TimeoutSeconds is < 1 or > 300 || settings.MaximumOutputBytes is < 1 or > 65536 || settings.MaximumFiles is < 1 or > 1000 || settings.MaximumArtifactBytes is < 1 or > 33554432 || settings.MaximumTotalBytes is < 1 or > 134217728)
            throw Error("cladding-configuration", "Local Skill paths or bounded process limits are invalid.");
    }
    private void EnsureRoot()
    {
        SafeAncestors(settings.StateRoot);
        Directory.CreateDirectory(settings.StateRoot);
        foreach (var name in new[] { "claims", "staging", "completed" }) { var path = Path.Combine(settings.StateRoot, name); SafeAncestors(path); Directory.CreateDirectory(path); }
    }
    // The injectable directory snapshot is internal and used only to reproduce exact cleanup
    // interleavings in tests. No request or model response can choose filesystem behavior.
    internal string[] ScanOutputFiles(string root, bool running = false, Func<string, string[]>? enumerate = null)
    {
        enumerate ??= path => Directory.EnumerateFileSystemEntries(path).Take(settings.MaximumFiles * 2 + 1).ToArray();
        bool Temporary(string path)
        {
            var relative = Path.GetRelativePath(root, path);
            return running && (relative == "_provider" || relative.StartsWith("_provider" + Path.DirectorySeparatorChar, StringComparison.Ordinal));
        }
        var files = new List<string>();
        var stack = new Stack<string>(); stack.Push(root);
        var entries = 0;
        while (stack.Count > 0)
        {
            var directory = stack.Pop();
            string[] children;
            try
            {
                SafeAncestors(directory); // Reject a queued directory replaced with a link.
                children = enumerate(directory);
            }
            catch (DirectoryNotFoundException) when (Temporary(directory)) { continue; }
            catch (FileNotFoundException) when (Temporary(directory)) { continue; }
            foreach (var entry in children)
            {
                if (++entries > settings.MaximumFiles * 2) throw Error("cladding-output-limit", "Too many output file-system entries.");
                FileAttributes attributes;
                try
                {
                    SafeAncestors(entry);
                    attributes = File.GetAttributes(entry);
                }
                catch (DirectoryNotFoundException) when (Temporary(entry)) { continue; }
                catch (FileNotFoundException) when (Temporary(entry)) { continue; }
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw Error("cladding-path", "Symlinks and reparse points are not permitted in review inputs or outputs.");
                if ((attributes & FileAttributes.Directory) != 0) stack.Push(entry);
                else
                {
                    files.Add(Path.GetRelativePath(root, entry).Replace('\\', '/'));
                    if (files.Count > settings.MaximumFiles) throw Error("cladding-output-limit", "Too many output artifacts.");
                }
            }
        }
        return files.ToArray();
    }
    private static void SafeAncestors(string path)
    {
        var current = Path.GetFullPath(path);
        while (true)
        {
            try
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw Error("cladding-path", "Symlinks and reparse points are not permitted in review inputs or outputs.");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
            var parent = Path.GetDirectoryName(current);
            if (parent is null || parent == current) break;
            current = parent;
        }
    }
    private static bool SafeRelative(string path) => !string.IsNullOrWhiteSpace(path) && path.Length <= 240 && !Path.IsPathRooted(path) && !path.Contains('\\') && !path.Contains(':') && path.Split('/').All(p => p.Length > 0 && p is not ("." or "..") && !p.Any(char.IsControl));
    private static bool Digest(string value) => value is { Length: 64 } && value.All(Uri.IsHexDigit);
    private static bool SameHash(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    private static string FileHash(string path) { SafeAncestors(path); using var stream = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(stream)); }
    private static byte[] ReadBytes(string path, long limit)
    {
        SafeAncestors(path);
        if (!File.Exists(path) || new FileInfo(path).Length is <= 0 || new FileInfo(path).Length > limit) throw Error("cladding-integrity", "Review metadata is missing, empty or oversized.");
        return File.ReadAllBytes(path);
    }
    private static T Read<T>(string path, long limit)
    {
        try { return StrictJson.Parse<T>(Encoding.UTF8.GetString(ReadBytes(path, limit))); }
        catch (JsonException) { throw Error("cladding-integrity", "Review metadata does not match the strict typed contract."); }
    }
    private static void WriteNew<T>(string path, T value)
    {
        SafeAncestors(path);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value, Protocol.Json);
        using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough);
        file.Write(bytes); file.Flush(true);
    }
    private static HarnessException Error(string code, string message) => new(code, message);
}
