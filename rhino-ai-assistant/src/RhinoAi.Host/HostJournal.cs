using System.Text.Json;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Host;

public enum TaskState { Planning, Running, WaitingUser, Review, Committed, Failed, Cancelled, Reverted }
public sealed record HostTaskRecord(Guid TaskId, TaskState State, Guid[] Operations, DateTimeOffset UpdatedAt, string? Error);
public sealed record JournalImage(int FormatVersion, OperationRecord[] Operations, HostTaskRecord[] Tasks);

/// <summary>
/// Single-writer durable local journal. Operation and task status share one atomically replaced image.
/// This is a flushed replacement file, not an append-only log or an ACID geometry transaction.
/// </summary>
public sealed class HostJournal : IDisposable
{
    private readonly string directory;
    private readonly string path;
    private readonly FileStream processLock;
    private readonly object gate = new();
    private Dictionary<Guid, OperationRecord> operations = [];
    private Dictionary<Guid, HostTaskRecord> tasks = [];
    private bool faulted;

    public HostJournal(string directory)
    {
        this.directory = directory;
        Directory.CreateDirectory(directory);
        path = Path.Combine(directory, "journal-v1.json");
        processLock = new FileStream(Path.Combine(directory, ".host.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        try
        {
            if (!File.Exists(path)) return;
            var image = JsonSerializer.Deserialize<JournalImage>(File.ReadAllBytes(path), StrictJson.Options)
                ?? throw new InvalidDataException("Empty journal.");
            if (image.FormatVersion != 1 || image.Operations is null || image.Tasks is null)
                throw new InvalidDataException("Unknown journal format.");
            operations = image.Operations.ToDictionary(x => x.OperationId);
            tasks = image.Tasks.ToDictionary(x => x.TaskId);
            ValidateImage();
            var changed = false;
            foreach (var record in operations.Values.ToArray())
            {
                if (record.State != OperationState.Applying) continue;
                var quarantined = record with { State = OperationState.FailedRecovery, Error = "Host restarted while applying; reconcile the actual Rhino model before any further operation. Automatic replay is blocked.", UpdatedAt = DateTimeOffset.UtcNow };
                operations[record.OperationId] = quarantined;
                tasks[record.Plan.Request.TaskId] = tasks[record.Plan.Request.TaskId] with { State = TaskState.Failed, Error = quarantined.Error, UpdatedAt = quarantined.UpdatedAt };
                changed = true;
            }
            if (changed) Persist(operations, tasks);
        }
        catch { processLock.Dispose(); throw; }
    }
    private void ValidateImage()
    {
        foreach (var record in operations.Values)
        {
            if (record is null || record.Plan is null || record.Plan.Request is null || record.OperationId == Guid.Empty || record.Plan.Request.OperationId != record.OperationId || record.RequestHash != record.Plan.RequestHash || record.RequestHash != PlanValidator.Prepare(new PrepareRequest(record.Plan.Request, record.Plan.Before, record.Plan.RestoreTarget)).RequestHash || !Enum.IsDefined(record.State))
                throw new InvalidDataException("Invalid persisted operation.");
            if (record.BeforeCheckpoint is null || record.BeforeCheckpoint.Snapshot is null || record.BeforeCheckpoint.Snapshot.SnapshotHash != record.Plan.Before.SnapshotHash || record.BeforeCheckpoint.DocumentId != record.Plan.Before.DocumentId)
                throw new InvalidDataException("Invalid before-image checkpoint.");
            if (record.State == OperationState.Committed)
                ValidateCompletion(record, new CompleteRequest(record.OperationId, record.RequestHash, record.State, record.Outcome, record.Error));
            else if (record.Outcome is not null) throw new InvalidDataException("Only committed outcomes may be persisted.");
            if (!tasks.TryGetValue(record.Plan.Request.TaskId, out var task) || !task.Operations.Contains(record.OperationId))
                throw new InvalidDataException("Missing task linkage.");
        }
        foreach (var task in tasks.Values)
            if (!Enum.IsDefined(task.State) || task.Operations is null || task.Operations.Any(id => !operations.TryGetValue(id, out var operation) || operation.Plan.Request.TaskId != task.TaskId))
                throw new InvalidDataException("Invalid persisted task.");
    }
    public void CheckHealth() { lock (gate) EnsureHealthy(); }
    public OperationRecord Get(Guid operationId)
    {
        lock (gate)
        {
            EnsureHealthy();
            return operations.TryGetValue(operationId, out var record) ? record : throw new HostHttpException(404, "operation_not_found", "Operation not found.");
        }
    }
    public ChangePlan Prepare(ChangePlan plan)
    {
        lock (gate)
        {
            EnsureHealthy();
            if (operations.TryGetValue(plan.Request.OperationId, out var existing))
            {
                AssertHash(existing, plan.RequestHash);
                if (existing.State == OperationState.FailedRecovery)
                    throw new HostHttpException(409, "recovery_required", "This operation requires model reconciliation; automatic replay is blocked.");
                // Retries receive the original plan; the caller must GET the operation before applying.
                return existing.Plan;
            }
            if (operations.Values.Any(x => x.Plan.Request.Expected.DocumentId == plan.Request.Expected.DocumentId && x.State == OperationState.FailedRecovery))
                throw new HostHttpException(409, "recovery_required", "The document has an unreconciled operation. New work is blocked.");
            var now = DateTimeOffset.UtcNow;
            var checkpoint = new Checkpoint(Guid.NewGuid(), plan.Before.DocumentId, now, plan.Before);
            var record = new OperationRecord(plan.Request.OperationId, plan.RequestHash, OperationState.Prepared, plan, checkpoint, null, null, now);
            Save(record);
            return plan;
        }
    }
    public OperationRecord Complete(CompleteRequest request)
    {
        lock (gate)
        {
            EnsureHealthy();
            if (!operations.TryGetValue(request.OperationId, out var existing))
                throw new HostHttpException(404, "operation_not_found", "Operation not found.");
            AssertHash(existing, request.RequestHash);
            if (request.State == OperationState.Prepared) throw new HostHttpException(400, "invalid_state", "Use prepare to create an operation; complete cannot acknowledge Prepared.");
            if (!Enum.IsDefined(request.State)) throw new HostHttpException(400, "invalid_state", "Unknown operation state.");
            if (existing.State == request.State)
            {
                if (Protocol.Hash(new { existing.Outcome, existing.Error }) != Protocol.Hash(new { request.Outcome, request.Error }))
                    throw new HostHttpException(409, "completion_conflict", "The stored completion differs from the retry.");
                return existing;
            }
            var allowed = (existing.State, request.State) switch
            {
                (OperationState.Prepared, OperationState.Applying or OperationState.Cancelled or OperationState.Rejected) => true,
                (OperationState.Applying, OperationState.Committed or OperationState.FailedRecovery) => true,
                // Only the authenticated plugin may reconcile its already durable verified outcome. No reapply.
                (OperationState.FailedRecovery, OperationState.Committed) => true,
                (OperationState.Applying or OperationState.FailedRecovery, OperationState.Cancelled) when request.Outcome is null && request.Error == "Cancelled before document mutation." => true,
                _ => false
            };
            if (!allowed) throw new HostHttpException(409, "state_conflict", "This operation transition is not allowed.");
            ValidateCompletion(existing, request);
            if (request.State == OperationState.Applying && operations.Values.Any(x => x.OperationId != existing.OperationId && x.Plan.Request.Expected.DocumentId == existing.Plan.Request.Expected.DocumentId && x.State is OperationState.Applying or OperationState.FailedRecovery))
                throw new HostHttpException(409, "document_busy", "Another operation is applying or requires recovery in this document.");
            var updated = existing with { State = request.State, Outcome = request.Outcome, Error = request.Error, UpdatedAt = DateTimeOffset.UtcNow };
            Save(updated);
            return updated;
        }
    }
    private static void ValidateCompletion(OperationRecord record, CompleteRequest request)
    {
        if (request.Error?.Length > 4096) throw new HostHttpException(400, "invalid_completion", "Error detail exceeds the limit.");
        if (request.State != OperationState.Committed)
        {
            if (request.Outcome is not null || (request.State == OperationState.Applying && request.Error is not null))
                throw new HostHttpException(400, "invalid_completion", "Only committed operations may carry an outcome; applying may not carry an error.");
            if (request.State == OperationState.FailedRecovery && string.IsNullOrWhiteSpace(request.Error))
                throw new HostHttpException(400, "invalid_completion", "Recovery requires a reason.");
            return;
        }
        var outcome = request.Outcome;
        if (request.Error is not null || outcome is null || outcome.After is null || outcome.UndoRecord == 0 || outcome.Added is null || outcome.Modified is null || outcome.Deleted is null || outcome.Issues is null || outcome.Issues.Length != 0)
            throw new HostHttpException(400, "invalid_completion", "Commit requires a verified outcome and an owned Undo record, with no QA issues.");
        var before = record.Plan.Before;
        var after = outcome.After;
        if (after.DocumentId != before.DocumentId || after.SessionId != before.SessionId || after.Revision <= before.Revision || after.Units != before.Units || after.Tolerance != before.Tolerance || after.Entities is null || after.Issues is null || after.Issues.Length != 0)
            throw new HostHttpException(400, "invalid_completion", "Outcome context does not match the approved document session or QA requirements.");
        if (after.Entities.Any(x => x is null || x.RhinoId == Guid.Empty || !x.IsValid || string.IsNullOrWhiteSpace(x.EntityId) || string.IsNullOrWhiteSpace(x.Fingerprint)) || after.Entities.Select(x => x.RhinoId).Distinct().Count() != after.Entities.Length || after.Entities.Select(x => x.EntityId).Distinct(StringComparer.Ordinal).Count() != after.Entities.Length)
            throw new HostHttpException(400, "invalid_completion", "Outcome contains invalid objects or duplicate identities.");
        PlanValidator.ValidateSnapshot(after);
        var beforeIds = before.Entities.Select(x => x.RhinoId).ToHashSet();
        var afterIds = after.Entities.Select(x => x.RhinoId).ToHashSet();
        var changedIds = before.Entities.Where(old => after.Entities.Any(current => current.RhinoId == old.RhinoId && current.Fingerprint != old.Fingerprint)).Select(x => x.RhinoId).ToHashSet();
        if (outcome.Added.Distinct().Count() != outcome.Added.Length || outcome.Modified.Distinct().Count() != outcome.Modified.Length || outcome.Deleted.Distinct().Count() != outcome.Deleted.Length || !changedIds.SetEquals(outcome.Modified))
            throw new HostHttpException(400, "invalid_completion", "Outcome contains duplicate or incorrect modified object IDs.");
        if (!afterIds.Except(beforeIds).ToHashSet().SetEquals(outcome.Added) || !beforeIds.Except(afterIds).ToHashSet().SetEquals(outcome.Deleted))
            throw new HostHttpException(400, "invalid_completion", "Outcome object changes do not match the snapshots.");
        if (record.Plan.Request.ToolId == "box.add")
        {
            if (outcome.Added.Length != 1 || outcome.Modified.Length != 0 || outcome.Deleted.Length != 0 || !before.Entities.All(entity => after.Entities.Any(x => x.RhinoId == entity.RhinoId && Protocol.Hash(x) == Protocol.Hash(entity))))
                throw new HostHttpException(400, "invalid_completion", "box.add must add exactly one object and preserve existing objects.");
            var added = after.Entities.Single(x => x.RhinoId == outcome.Added[0]);
            if (added.EntityId != record.Plan.Request.EntityId)
                throw new HostHttpException(400, "invalid_completion", "Added business identity does not match the approved plan.");
        }
        else if (record.Plan.Request.ToolId == "checkpoint.restore")
        {
            var target = record.Plan.RestoreTarget?.Snapshot ?? throw new HostHttpException(400, "invalid_completion", "Restore target missing from plan.");
            if (after.Entities.Length != target.Entities.Length || !target.Entities.All(entity => after.Entities.Any(x => Protocol.Hash(x) == Protocol.Hash(entity))))
                throw new HostHttpException(400, "invalid_completion", "Restore outcome differs from the approved managed checkpoint.");
        }
        else if (record.Plan.Request.ToolId == "object.translate")
        {
            if (outcome.Added.Length != 0 || outcome.Deleted.Length != 0 || outcome.Modified.Length != 1 || outcome.Modified[0] != record.Plan.Request.ObjectId || !before.Entities.Where(x => x.RhinoId != record.Plan.Request.ObjectId).All(entity => after.Entities.Any(x => x.RhinoId == entity.RhinoId && Protocol.Hash(x) == Protocol.Hash(entity))))
                throw new HostHttpException(400, "invalid_completion", "object.translate must modify only the approved object.");
            var oldEntity = before.Entities.Single(x => x.RhinoId == record.Plan.Request.ObjectId);
            var newEntity = after.Entities.Single(x => x.RhinoId == record.Plan.Request.ObjectId);
            if (oldEntity.EntityId != newEntity.EntityId || oldEntity.Fingerprint == newEntity.Fingerprint)
                throw new HostHttpException(400, "invalid_completion", "Translation requires a changed fingerprint and preserved business identity.");
        }
    }
    private static void AssertHash(OperationRecord record, string? hash)
    {
        if (!string.Equals(record.RequestHash, hash, StringComparison.Ordinal))
            throw new HostHttpException(409, "operation_payload_conflict", "This operation ID is already associated with another request hash.");
    }
    private void Save(OperationRecord record)
    {
        var nextOperations = new Dictionary<Guid, OperationRecord>(operations) { [record.OperationId] = record };
        var taskId = record.Plan.Request.TaskId;
        var operationIds = tasks.TryGetValue(taskId, out var task) ? task.Operations.Append(record.OperationId).Distinct().ToArray() : [record.OperationId];
        var taskOperations = nextOperations.Values.Where(x => x.Plan.Request.TaskId == taskId).ToArray();
        var state = taskOperations.Any(x => x.State == OperationState.FailedRecovery) ? TaskState.Failed
            : taskOperations.Any(x => x.State == OperationState.Applying) ? TaskState.Running
            : taskOperations.Any(x => x.State == OperationState.Prepared) ? TaskState.Review
            : taskOperations.Any(x => x.State == OperationState.Committed) ? TaskState.Committed : TaskState.Cancelled;
        var taskError = taskOperations.Where(x => x.State == OperationState.FailedRecovery).OrderByDescending(x => x.UpdatedAt).FirstOrDefault()?.Error;
        var nextTasks = new Dictionary<Guid, HostTaskRecord>(tasks) { [taskId] = new HostTaskRecord(taskId, state, operationIds, record.UpdatedAt, taskError) };
        Persist(nextOperations, nextTasks);
        operations = nextOperations;
        tasks = nextTasks;
    }
    private void Persist(Dictionary<Guid, OperationRecord> nextOperations, Dictionary<Guid, HostTaskRecord> nextTasks)
    {
        var temporary = Path.Combine(directory, $".journal-{Guid.NewGuid():N}.tmp");
        try
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(new JournalImage(1, nextOperations.Values.OrderBy(x => x.OperationId).ToArray(), nextTasks.Values.OrderBy(x => x.TaskId).ToArray()), StrictJson.Options);
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }
            File.Move(temporary, path, overwrite: true);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            // A storage failure may be ambiguous. Quarantine the host until restart/reconciliation.
            faulted = true;
            throw new HostHttpException(503, "storage_failure", "Journal durability failed. Stop model mutation and reconcile before retrying.");
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
    }
    private void EnsureHealthy()
    {
        if (faulted) throw new HostHttpException(503, "storage_failure", "The journal is quarantined after a storage failure. Restart and reconcile before retrying.");
    }
    public void Dispose() => processLock.Dispose();
}
