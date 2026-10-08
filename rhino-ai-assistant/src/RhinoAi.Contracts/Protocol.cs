using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RhinoAi.Contracts;

public static class Protocol
{
    public const int Version = 1;
    public const string EntityKey = "RhinoAi.EngineeringEntityId";
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = true, UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, Converters = { new JsonStringEnumConverter() } };
    public static string Hash<T>(T value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, Json))));
}
public sealed record Point3(double X, double Y, double Z);
public sealed record BoxSpec(Point3 Origin, double Width, double Depth, double Height);
public sealed record EntitySnapshot(Guid RhinoId, string EntityId, string Fingerprint, string GeometryJson, string AttributesJson, string Kind, bool IsValid);
public sealed record DocumentSnapshot(Guid DocumentId, Guid SessionId, long Revision, string Units, double Tolerance, EntitySnapshot[] Entities, string[] Issues)
{
    public string SnapshotHash => Protocol.Hash(new { DocumentId, SessionId, Revision, Units, Tolerance, Entities });
}
public sealed record ExpectedContext(Guid DocumentId, Guid SessionId, long Revision, string SnapshotHash);
public sealed record ToolRequest(int ProtocolVersion, Guid TaskId, Guid OperationId, string ToolId, ExpectedContext Expected, BoxSpec? Box = null, Guid? ObjectId = null, Point3? Translation = null, string? EntityId = null, Guid? CheckpointId = null);
public sealed record ChangePlan(ToolRequest Request, string RequestHash, DocumentSnapshot Before, string Summary, string[] Warnings, Checkpoint? RestoreTarget = null);
public enum OperationState { Prepared, Applying, Committed, Cancelled, Rejected, FailedRecovery }
public sealed record Checkpoint(Guid CheckpointId, Guid DocumentId, DateTimeOffset CreatedAt, DocumentSnapshot Snapshot, string Scope = "managed-objects");
public sealed record ApplyOutcome(DocumentSnapshot After, Guid[] Added, Guid[] Modified, Guid[] Deleted, uint UndoRecord, string[] Issues);
public sealed record OperationRecord(Guid OperationId, string RequestHash, OperationState State, ChangePlan Plan, Checkpoint? BeforeCheckpoint, ApplyOutcome? Outcome, string? Error, DateTimeOffset UpdatedAt);
public sealed record PrepareRequest(ToolRequest Request, DocumentSnapshot Snapshot, Checkpoint? RestoreTarget = null);
public sealed record CompleteRequest(Guid OperationId, string RequestHash, OperationState State, ApplyOutcome? Outcome, string? Error);
public sealed record ApiError(string Code, string Message);
public sealed class HarnessException(string code, string message) : Exception(message) { public string Code { get; } = code; }

/// <summary>Every method is synchronous and MUST be invoked through IUiDispatcher. Values returned are detached.</summary>
public interface IDocumentAdapter
{
    DocumentSnapshot Capture();
    void ShowPreview(ChangePlan plan);
    void ClearPreview();
    Checkpoint CaptureCheckpoint();
    // Must revalidate context, own Undo record, apply+verify synchronously, and compensate partial failure where possible.
    ApplyOutcome Apply(ChangePlan plan);
    // Explicit scope acceptance and expected-current-context are mandatory. Preserves unmanaged objects.
    ApplyOutcome Restore(Checkpoint checkpoint, ExpectedContext expectedCurrent);
}
public interface IUiDispatcher { Task<T> InvokeAsync<T>(Func<T> action, CancellationToken cancellationToken = default); }
