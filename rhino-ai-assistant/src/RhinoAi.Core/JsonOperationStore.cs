using System.Text.Json;
using RhinoAi.Contracts;
namespace RhinoAi.Core;

public interface IOperationStore
{
    OperationRecord? Get(Guid operationId);
    IReadOnlyList<OperationRecord> List();
    void Put(OperationRecord record);
}
/// <summary>Single-writer durable per-operation files. The lock prevents two local processes sharing this store.</summary>
public sealed class JsonOperationStore : IOperationStore, IDisposable
{
    private readonly string _directory;
    private readonly FileStream _lease;
    private readonly object _sync = new();
    public JsonOperationStore(string directory)
    {
        _directory = Path.GetFullPath(directory);
        Directory.CreateDirectory(_directory);
        _lease = new FileStream(Path.Combine(_directory, ".writer.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
    }
    private string PathFor(Guid id) => Path.Combine(_directory, id.ToString("D") + ".json");
    public OperationRecord? Get(Guid operationId)
    {
        lock (_sync)
        {
            string path = PathFor(operationId);
            if (!File.Exists(path)) return null;
            return ReadVerified(path);
        }
    }
    public IReadOnlyList<OperationRecord> List()
    {
        lock (_sync)
            return Directory.GetFiles(_directory, "*.json").Order(StringComparer.Ordinal).Select(ReadVerified).ToArray();
    }
    private static OperationRecord ReadVerified(string path)
    {
        var record = JsonSerializer.Deserialize<OperationRecord>(File.ReadAllText(path), Protocol.Json) ?? throw new InvalidDataException("Operation journal is invalid.");
        try
        {
            if (Path.GetFileNameWithoutExtension(path) != record.OperationId.ToString("D")) throw new InvalidDataException("Journal filename does not match operation identity.");
            if (record.Plan is null || record.Plan.Request is null || record.OperationId != record.Plan.Request.OperationId || record.RequestHash != record.Plan.RequestHash || !Enum.IsDefined(record.State)) throw new InvalidDataException("Journal operation identity/state is inconsistent.");
            var plan = PlanValidator.Prepare(new(record.Plan.Request, record.Plan.Before, record.Plan.RestoreTarget));
            if (record.RequestHash != plan.RequestHash) throw new InvalidDataException("Journal payload hash does not match its stored plan.");
            if (record.State is OperationState.Applying or OperationState.Committed or OperationState.FailedRecovery && record.BeforeCheckpoint is null) throw new InvalidDataException("Applying operation lacks its durable before-images.");
            if (record.BeforeCheckpoint is not null && (record.BeforeCheckpoint.DocumentId != plan.Before.DocumentId || record.BeforeCheckpoint.Snapshot.SnapshotHash != plan.Before.SnapshotHash)) throw new InvalidDataException("Journal before-image does not match approved context.");
            if (record.State == OperationState.Committed) ExecutionCoordinator.ValidateOutcome(plan, record.Outcome ?? throw new InvalidDataException("Committed outcome missing."));
            return record;
        }
        catch (HarnessException ex) { throw new InvalidDataException("Journal validation failed: " + ex.Code, ex); }
    }
    public void Put(OperationRecord record)
    {
        lock (_sync)
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(record, Protocol.Json);
            var destination = PathFor(record.OperationId);
            var temporary = destination + ".tmp-" + Guid.NewGuid().ToString("N");
            try
            {
                using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough)) { stream.Write(bytes); stream.Flush(true); }
                File.Move(temporary, destination, true);
                // A successful flush+atomic replacement protects process-crash recovery. Sudden power loss/FS durability still depends on the OS and storage; no ACID guarantee.
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
    }
    public void Dispose() => _lease.Dispose();
}
