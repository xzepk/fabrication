using RhinoAi.Contracts;
namespace RhinoAi.Core;

/// <summary>Owns a single adapter/document execution queue. Network and user waits stay outside Rhino Undo.</summary>
public sealed class ExecutionCoordinator(IDocumentAdapter adapter, IUiDispatcher dispatcher, IOperationStore store)
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private Guid? _previewOperationId;
    public async Task<ChangePlan> PreviewAsync(ChangePlan plan, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            EnsureNoUncertainOperations();
            var canonical = PlanValidator.Prepare(new(plan.Request, plan.Before, plan.RestoreTarget));
            if (canonical.RequestHash != plan.RequestHash) throw new HarnessException("payload-mismatch", "Plan request hash is invalid.");
            var existing = store.Get(plan.Request.OperationId);
            if (existing is not null)
            {
                MatchHash(existing, plan.RequestHash);
                if (existing.State != OperationState.Prepared) throw new HarnessException("operation-terminal", "Use a fresh operation ID for a new preview.");
            }
            await dispatcher.InvokeAsync(() => { PlanValidator.Match(plan.Request.Expected, adapter.Capture()); return 0; }, cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            store.Put(new(plan.Request.OperationId, plan.RequestHash, OperationState.Prepared, canonical, null, null, null, DateTimeOffset.UtcNow));
            await dispatcher.InvokeAsync(() => { adapter.ShowPreview(canonical); return 0; }, cancellationToken);
            _previewOperationId = plan.Request.OperationId;
            return canonical;
        }
        finally { _gate.Release(); }
    }
    public async Task<OperationRecord> CommitAsync(Guid operationId, CancellationToken cancellationToken = default, Func<OperationRecord, Task>? beforeApply = null)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var record = Required(operationId);
            // Lost ACK replay returns the durable result, including after native Undo; never reapplies.
            if (record.State == OperationState.Committed) return record;
            if (record.State != OperationState.Prepared) throw new HarnessException("operation-state", "Only a prepared, accepted preview can commit.");
            if (_previewOperationId != operationId) throw new HarnessException("preview-required", "This operation is not the currently displayed preview. Prepare it again before acceptance.");
            EnsureNoUncertainOperations();
            var checkpoint = await dispatcher.InvokeAsync(() =>
            {
                var now = adapter.Capture();
                PlanValidator.ValidateSnapshot(now);
                PlanValidator.Match(record.Plan.Request.Expected, now);
                return adapter.CaptureCheckpoint();
            }, cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (checkpoint.Scope != "managed-objects" || checkpoint.DocumentId != record.Plan.Before.DocumentId || checkpoint.Snapshot.SnapshotHash != record.Plan.Before.SnapshotHash) throw new HarnessException("checkpoint-mismatch", "Before-images do not match the accepted preview context.");
            record = record with { BeforeCheckpoint = checkpoint, State = OperationState.Applying, UpdatedAt = DateTimeOffset.UtcNow };
            store.Put(record); // Durable before-images BEFORE mutation. Failure here means no apply.
            bool mutationStarted = false;
            try
            {
                if (beforeApply is not null) await beforeApply(record); // IPC before document mutation and outside any Undo record.
                // Cancellation is honored until synchronous adapter mutation starts, including during IPC and UI queue waits.
                var outcome = await dispatcher.InvokeAsync(() =>
                {
                    PlanValidator.Match(record.Plan.Request.Expected, adapter.Capture());
                    cancellationToken.ThrowIfCancellationRequested();
                    mutationStarted = true; // No await, network, user wait, or cancellation inside the adapter mutation.
                    return record.Plan.RestoreTarget is not null
                        ? adapter.Restore(record.Plan.RestoreTarget, record.Plan.Request.Expected)
                        : adapter.Apply(record.Plan);
                });
                ValidateOutcome(record.Plan, outcome);
                record = record with { State = OperationState.Committed, Outcome = outcome, UpdatedAt = DateTimeOffset.UtcNow };
                store.Put(record); // ACK is allowed only after verified durable outcome.
                await dispatcher.InvokeAsync(() => { adapter.ClearPreview(); return 0; });
                return record;
            }
            catch (OperationCanceledException) when (!mutationStarted)
            {
                var cancelled = record with { State = OperationState.Cancelled, Error = "Cancelled before document mutation.", UpdatedAt = DateTimeOffset.UtcNow };
                store.Put(cancelled);
                await dispatcher.InvokeAsync(() => { adapter.ClearPreview(); return 0; });
                throw;
            }
            catch (Exception e)
            {
                var failed = record with { State = OperationState.FailedRecovery, Error = e.Message, UpdatedAt = DateTimeOffset.UtcNow };
                try { store.Put(failed); } catch { /* Existing durable Applying record still quarantines replay. */ }
                try { await dispatcher.InvokeAsync(() => { adapter.ClearPreview(); return 0; }); } catch { }
                throw new HarnessException("recovery-required", "Apply or durable acknowledgement failed. Automatic replay is blocked; inspect checkpoint and actual document. " + e.Message);
            }
        }
        finally { _gate.Release(); }
    }
    public async Task<OperationRecord> RejectAsync(Guid operationId, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var record = Required(operationId);
            if (record.State == OperationState.Cancelled) return record;
            if (record.State != OperationState.Prepared) throw new HarnessException("operation-state", "An applying/completed task cannot be cancelled as if it had not run.");
            record = record with { State = OperationState.Cancelled, UpdatedAt = DateTimeOffset.UtcNow };
            store.Put(record);
            await dispatcher.InvokeAsync(() => { adapter.ClearPreview(); return 0; }, cancellationToken);
            return record;
        }
        finally { _gate.Release(); }
    }
    public OperationRecord? Get(Guid id) => store.Get(id);
    private OperationRecord Required(Guid id) => store.Get(id) ?? throw new HarnessException("not-found", "Operation was not prepared in this executor.");
    private void EnsureNoUncertainOperations()
    {
        if (store.List().Any(r => r.State is OperationState.Applying or OperationState.FailedRecovery)) throw new HarnessException("recovery-required", "An uncertain operation exists. Recovery must be reconciled before further mutation.");
    }
    private static void MatchHash(OperationRecord r, string hash) { if (r.RequestHash != hash) throw new HarnessException("operation-conflict", "Operation ID was already used with different arguments."); }
    public static void ValidateOutcome(ChangePlan plan, ApplyOutcome outcome)
    {
        PlanValidator.ValidateSnapshot(outcome.After);
        if (outcome.UndoRecord == 0 || outcome.Issues.Length != 0 || outcome.After.DocumentId != plan.Before.DocumentId || outcome.After.SessionId != plan.Before.SessionId || outcome.After.Revision <= plan.Before.Revision) throw new HarnessException("effect-mismatch", "Invalid Undo ownership, context, revision or post-effect QA.");
        if (plan.Request.ToolId == "box.add")
        {
            if (outcome.Added.Length != 1 || outcome.Modified.Length != 0 || outcome.Deleted.Length != 0 || outcome.After.Entities.Length != plan.Before.Entities.Length + 1 || outcome.After.Entities.Count(e => e.EntityId == plan.Request.EntityId && e.RhinoId == outcome.Added[0]) != 1) throw new HarnessException("effect-mismatch", "Actual created objects differ from approved plan.");
            foreach (var before in plan.Before.Entities) if (!outcome.After.Entities.Any(e => e.RhinoId == before.RhinoId && e.Fingerprint == before.Fingerprint)) throw new HarnessException("effect-mismatch", "Unrelated managed geometry changed.");
        }
        else if (plan.Request.ToolId == "cladding.plates.add")
        {
            var plates = plan.Request.Plates ?? throw new HarnessException("effect-mismatch", "Approved plate batch is missing.");
            var oldIds = plan.Before.Entities.Select(e => e.RhinoId).ToHashSet();
            var actualAdded = outcome.After.Entities.Where(e => !oldIds.Contains(e.RhinoId)).ToArray();
            if (outcome.Added.Length != plates.Length || outcome.Added.Distinct().Count() != plates.Length ||
                outcome.Modified.Length != 0 || outcome.Deleted.Length != 0 || outcome.After.Entities.Length != plan.Before.Entities.Length + plates.Length ||
                !actualAdded.Select(e => e.RhinoId).ToHashSet().SetEquals(outcome.Added) ||
                !actualAdded.Select(e => e.EntityId).ToHashSet(StringComparer.Ordinal).SetEquals(plates.Select(p => p.EntityId)))
                throw new HarnessException("effect-mismatch", "Actual plate identities/count differ from the exact approved batch.");
            foreach (var before in plan.Before.Entities)
                if (!outcome.After.Entities.Any(e => e.RhinoId == before.RhinoId && e.EntityId == before.EntityId && e.Fingerprint == before.Fingerprint))
                    throw new HarnessException("effect-mismatch", "An existing managed object changed during plate creation.");
        }
        else if (plan.Request.ToolId == "checkpoint.restore")
        {
            var target = plan.RestoreTarget ?? throw new HarnessException("invalid-restore", "Restore target is missing.");
            if (outcome.After.Entities.Length != target.Snapshot.Entities.Length) throw new HarnessException("effect-mismatch", "Restored managed object count differs from checkpoint.");
            foreach (var wanted in target.Snapshot.Entities)
                if (!outcome.After.Entities.Any(e => e.EntityId == wanted.EntityId && e.Fingerprint == wanted.Fingerprint)) throw new HarnessException("effect-mismatch", "Restored geometry/identity differs from checkpoint.");
        }
        else if (plan.Request.ToolId == "object.translate")
        {
            if (outcome.Added.Length != 0 || outcome.Modified.Length != 1 || outcome.Modified[0] != plan.Request.ObjectId || outcome.Deleted.Length != 0 || outcome.After.Entities.Length != plan.Before.Entities.Length) throw new HarnessException("effect-mismatch", "Actual translated object count differs from approved plan.");
            var oldTarget = plan.Before.Entities.Single(e => e.RhinoId == plan.Request.ObjectId);
            var newTarget = outcome.After.Entities.SingleOrDefault(e => e.RhinoId == plan.Request.ObjectId);
            if (newTarget is null || newTarget.EntityId != oldTarget.EntityId || newTarget.Fingerprint == oldTarget.Fingerprint) throw new HarnessException("effect-mismatch", "Translated target identity or geometry differs from the approved effect.");
            foreach (var before in plan.Before.Entities) if (before.RhinoId != plan.Request.ObjectId && !outcome.After.Entities.Any(e => e.RhinoId == before.RhinoId && e.Fingerprint == before.Fingerprint)) throw new HarnessException("effect-mismatch", "Unrelated managed geometry changed.");
        }
    }
}
