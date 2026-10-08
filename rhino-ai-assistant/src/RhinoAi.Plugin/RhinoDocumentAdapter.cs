using System.Text.Json;
using Rhino;
using Rhino.Commands;
using Rhino.DocObjects;
using Rhino.DocObjects.Tables;
using Rhino.FileIO;
using Rhino.Geometry;
using Rhino.Runtime;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Plugin;

/// <summary>
/// A document-bound adapter. Every public method and all geometry access runs on Rhino's UI thread.
/// Event handlers only invalidate detached state; actual reconciliation occurs at the next capture/idle.
/// </summary>
public sealed class RhinoDocumentAdapter : IDocumentAdapter, IDisposable
{
    public const string DocumentKey = "RhinoAi.DocumentId";
    private const string KindKey = "RhinoAi.Kind";
    private readonly RhinoDoc _doc;
    private readonly Guid _sessionId = Guid.NewGuid();
    private Guid _documentId;
    private long _revision = DateTime.UtcNow.Ticks;
    private bool _closed;
    private bool _dirty;
    private bool _applying;
    private bool _previewInvalid;
    private string? _previewRequestHash;
    private Guid? _previewRestoreId;
    private string? _previewRestoreHash;
    private DetachedPreviewConduit? _preview;
    private string? _unsafeLineage;
    private string? _lastContentHash;
    private string? _commandBeforeHash;
    private string? _observedCommand;
    private readonly HashSet<string> _lineageCommands = new(StringComparer.OrdinalIgnoreCase)
        { "Split", "Join", "BooleanUnion", "BooleanDifference", "BooleanIntersection", "BooleanSplit", "Explode", "Trim", "Untrim", "MergeAllFaces" };
    private static readonly SerializationOptions Serialization = new() { RhinoVersion = 8, WriteUserData = true, WriteRenderMeshes = false, WriteAnalysisMeshes = false };
    public event EventHandler? Invalidated;
    public uint RuntimeSerial => _doc.RuntimeSerialNumber;

    public RhinoDocumentAdapter(RhinoDoc document)
    {
        RhinoUiDispatcher.RequireUiThread();
        _doc = document;
        Guid.TryParse(_doc.Strings.GetValue(DocumentKey), out _documentId);
        if (_documentId != Guid.Empty && File.Exists(LineageFile)) _unsafeLineage = File.ReadAllText(LineageFile);
        RhinoDoc.AddRhinoObject += ObjectChanged;
        RhinoDoc.DeleteRhinoObject += ObjectChanged;
        RhinoDoc.UndeleteRhinoObject += ObjectChanged;
        RhinoDoc.ReplaceRhinoObject += ObjectReplaced;
        RhinoDoc.ModifyObjectAttributes += AttributesChanged;
        RhinoDoc.DocumentPropertiesChanged += DocumentChanged;
        RhinoDoc.LayerTableEvent += LayerChanged;
        RhinoDoc.MaterialTableEvent += MaterialChanged;
        RhinoDoc.LinetypeTableEvent += LinetypeChanged;
        RhinoDoc.GroupTableEvent += GroupChanged;
        RhinoDoc.CloseDocument += DocumentClosed;
        RhinoDoc.BeginOpenDocument += DocumentOpening;
        RhinoDoc.EndOpenDocument += DocumentOpening;
        RhinoDoc.ActiveDocumentChanged += ActiveDocumentChanged;
        Command.UndoRedo += UndoRedo;
        Command.BeginCommand += BeginCommand;
        Command.EndCommand += EndCommand;
        RhinoApp.Idle += OnIdle;
    }

    /// <summary>Explicit UI action; this is the only bootstrap metadata write, never performed by Capture/Preview.</summary>
    public void InitializeDocument()
    {
        EnsureOpen();
        if (_documentId != Guid.Empty) return;
        if (!string.IsNullOrWhiteSpace(_doc.Strings.GetValue(DocumentKey)) || AllObjects().Any(x => !string.IsNullOrEmpty(x.Attributes.GetUserString(Protocol.EntityKey))))
            throw new HarnessException("identity-corrupt", "Document identity is missing/corrupt while metadata or managed entities already exist. Explicit manual identity reconciliation is required; no new identity was assigned.");
        var record = _doc.BeginUndoRecord("Initialize Rhino AI document identity");
        if (record == 0) throw new HarnessException("undo-unavailable", "Document identity was not initialized: Undo is unavailable or another record is active.");
        try
        {
            var id = Guid.NewGuid();
            _doc.Strings.SetString(DocumentKey, id.ToString("D"));
            if (_doc.Strings.GetValue(DocumentKey) != id.ToString("D")) throw new HarnessException("identity-write", "Cannot persist the document identity.");
            _documentId = id;
            BumpRevision();
        }
        finally
        {
            if (_doc.CurrentUndoRecordSerialNumber != record || !_doc.EndUndoRecord(record)) throw new HarnessException("undo-close", "Could not close the owned identity Undo record. Review the document before proceeding.");
        }
    }

    public DocumentSnapshot Capture()
    {
        EnsureOpen();
        if (_documentId == Guid.Empty) throw new HarnessException("document-uninitialized", "Click Initialize document before preparing an operation. Save the 3DM to persist its identity.");
        var issues = new List<string>();
        if (!Guid.TryParse(_doc.Strings.GetValue(DocumentKey), out var stored) || stored != _documentId)
            issues.Add("Persistent document identity changed or disappeared; reopen the document before continuing.");
        if (_unsafeLineage is not null) issues.Add(_unsafeLineage);
        var entities = new List<EntitySnapshot>();
        foreach (var obj in AllObjects())
        {
            var entityId = obj.Attributes.GetUserString(Protocol.EntityKey);
            if (string.IsNullOrEmpty(entityId)) continue;
            var snapshot = Snapshot(obj);
            if (obj.Attributes.GroupCount != 0 || obj.Attributes.LinetypeIndex > 0 || _doc.Layers[obj.Attributes.LayerIndex].LinetypeIndex > 0)
                issues.Add($"Managed entity {entityId} uses groups or custom linetypes outside the Stage 1 checkpoint scope.");
            entities.Add(snapshot);
            if (!snapshot.IsValid) issues.Add($"Managed entity {entityId} ({obj.Id}) is invalid or no longer a supported box Brep.");
            if (obj.IsReference) issues.Add($"Managed entity {entityId} is a reference object and cannot be managed safely.");
        }
        foreach (var group in entities.GroupBy(x => x.EntityId, StringComparer.Ordinal).Where(x => x.Count() > 1))
            issues.Add($"Duplicate EngineeringEntityId '{group.Key}' on {string.Join(", ", group.Select(x => x.RhinoId))}. Explicit identity reconciliation is required.");
        entities.Sort((a, b) => a.RhinoId.CompareTo(b.RhinoId));
        // Snapshot fingerprint detects even mutations for which Rhino sent no observed object event.
        var contentHash = Protocol.Hash(new { Units = _doc.ModelUnitSystem.ToString(), Tolerance = _doc.ModelAbsoluteTolerance, Entities = entities });
        if (_lastContentHash is not null && _lastContentHash != contentHash) BumpRevision();
        _lastContentHash = contentHash;
        _dirty = false;
        return new(_documentId, _sessionId, _revision, _doc.ModelUnitSystem.ToString(), _doc.ModelAbsoluteTolerance, entities.ToArray(), issues.ToArray());
    }

    public Checkpoint CaptureCheckpoint() => new(Guid.NewGuid(), _documentId, DateTimeOffset.UtcNow, Capture());

    public void ShowPreview(ChangePlan plan)
    {
        ValidatePlan(plan);
        ClearPreview();
        _preview = new DetachedPreviewConduit(RuntimeSerial, plan.RestoreTarget is not null ? plan.RestoreTarget.Snapshot.Entities.Select(DeserializeGeometry).ToArray() : [BuildResultGeometry(plan)]);
        _previewRestoreId = plan.RestoreTarget?.CheckpointId;
        _previewRestoreHash = plan.RestoreTarget is null ? null : Protocol.Hash(plan.RestoreTarget);
        _previewRequestHash = plan.RequestHash;
        _previewInvalid = false;
        _preview.Enabled = true;
        _doc.Views.Redraw();
    }

    public void ClearPreview()
    {
        RhinoUiDispatcher.RequireUiThread();
        _preview?.Dispose(); _preview = null; _previewRequestHash = null; _previewRestoreId = null; _previewRestoreHash = null; _previewInvalid = false;
        if (!_closed) _doc.Views.Redraw();
    }

    public ApplyOutcome Apply(ChangePlan plan)
    {
        var before = ValidatePlan(plan);
        if (_preview is null || _previewInvalid || _previewRequestHash != plan.RequestHash)
            throw new HarnessException("preview-required", "This exact plan needs a current, accepted preview before commit.");
        using var result = BuildResultGeometry(plan);
        var id = plan.Request.ToolId == "box.add" ? Guid.NewGuid() : plan.Request.ObjectId!.Value;
        using var attributes = plan.Request.ToolId == "box.add" ? _doc.CreateDefaultAttributes() : _doc.Objects.FindId(id).Attributes.Duplicate();
        if (plan.Request.ToolId == "box.add")
        {
            attributes.ObjectId = id;
            attributes.SetUserString(Protocol.EntityKey, plan.Request.EntityId!);
            attributes.SetUserString(KindKey, "box");
            attributes.SetUserString("RhinoAi.CreatedOperation", plan.Request.OperationId.ToString("D"));
            attributes.SetUserString("RhinoAi.CreatedTask", plan.Request.TaskId.ToString("D"));
        }
        attributes.SetUserString("RhinoAi.LastOperation", plan.Request.OperationId.ToString("D"));
        attributes.SetUserString("RhinoAi.Actor", "RhinoAi.Stage1");
        var expectedGeometry = result.ToJSON(Serialization);
        return InOwnedRecord("Rhino AI: " + plan.Summary, before, () =>
        {
            if (plan.Request.ToolId == "box.add")
            {
                if (_doc.Objects.Add(result, attributes) != id) throw new HarnessException("add-failed", "Rhino did not add the expected object identity.");
            }
            else
            {
                if (!_doc.Objects.Replace(id, result, false)) throw new HarnessException("replace-failed", "Rhino did not replace the selected object geometry.");
                if (!_doc.Objects.ModifyAttributes(id, attributes, true)) throw new HarnessException("attributes-failed", "Rhino did not retain the operation provenance.");
            }
            var actual = _doc.Objects.FindId(id) ?? throw new HarnessException("post-qa", "Expected object missing after apply.");
            if (!actual.Geometry.IsValid || actual.Geometry.ToJSON(Serialization) != expectedGeometry)
                throw new HarnessException("post-qa", "Rhino geometry does not match the detached requested result.");
            if (actual.Attributes.GetUserString(Protocol.EntityKey) != attributes.GetUserString(Protocol.EntityKey))
                throw new HarnessException("post-qa", "Engineering identity changed unexpectedly.");
        }, plan: plan);
    }

    public ApplyOutcome Restore(Checkpoint checkpoint, ExpectedContext expectedCurrent)
    {
        var before = Capture();
        CheckExpected(expectedCurrent, before);
        if (_preview is null || _previewInvalid || _previewRestoreId != checkpoint.CheckpointId || _previewRestoreHash != Protocol.Hash(checkpoint))
            throw new HarnessException("preview-required", "The checkpoint needs an accepted current preview before restore.");
        if (checkpoint.Scope != "managed-objects" || checkpoint.DocumentId != before.DocumentId || checkpoint.Snapshot.DocumentId != before.DocumentId)
            throw new HarnessException("restore-scope", "Checkpoint must belong to this document and the supported managed-object scope.");
        if (checkpoint.Snapshot.Issues.Length != 0 || checkpoint.Snapshot.Entities.Any(x => !x.IsValid) || checkpoint.Snapshot.Entities.Select(x => x.EntityId).Distinct().Count() != checkpoint.Snapshot.Entities.Length)
            throw new HarnessException("restore-invalid", "Checkpoint geometry or identities are invalid.");
        if (checkpoint.Snapshot.Units != before.Units || checkpoint.Snapshot.Tolerance != before.Tolerance)
            throw new HarnessException("restore-context", "Units/tolerance differ from the checkpoint. No implicit scaling is supported.");
        // Preflight all serialization and every GUID collision before any mutation.
        foreach (var entity in checkpoint.Snapshot.Entities)
        {
            using var geometry = DeserializeGeometry(entity);
            using var attrs = DeserializeAttributes(entity);
            var live = _doc.Objects.FindId(entity.RhinoId);
            if (live is not null && (live.IsLocked || _doc.Layers[live.Attributes.LayerIndex].IsLocked)) throw new HarnessException("restore-locked", "Unlock affected managed objects/layers before preparing restore.");
            if (live is not null && string.IsNullOrEmpty(live.Attributes.GetUserString(Protocol.EntityKey)))
                throw new HarnessException("restore-collision", "Checkpoint Rhino GUID is occupied by an unmanaged object.");
            ValidateAttributeReferences(attrs, ReadEnvelope(entity));
        }
        var result = InOwnedRecord("Rhino AI: Restore managed checkpoint " + checkpoint.CheckpointId, before,
            () => ReplaceManaged(checkpoint.Snapshot), allowExistingIssues: true);
        _unsafeLineage = null;
        return result with { After = Capture() };
    }

    private ApplyOutcome InOwnedRecord(string description, DocumentSnapshot before, Action mutation, bool allowExistingIssues = false, ChangePlan? plan = null)
    {
        if (!allowExistingIssues && before.Issues.Length != 0) throw new HarnessException("qa-blocked", string.Join("\n", before.Issues));
        var unmanaged = UnmanagedFingerprints();
        var record = _doc.BeginUndoRecord(description);
        if (record == 0) throw new HarnessException("undo-unavailable", "BeginUndoRecord returned 0. Nothing was changed.");
        _applying = true;
        DocumentSnapshot? after = null;
        Exception? failure = null;
        try
        {
            mutation();
            if (_doc.CurrentUndoRecordSerialNumber != record) throw new HarnessException("undo-ownership", "Undo ownership changed during the synchronous operation.");
            BumpRevision();
            after = Capture();
            if (after.Issues.Any(x => x != _unsafeLineage)) throw new HarnessException("post-qa", string.Join("\n", after.Issues));
            if (Protocol.Hash(unmanaged) != Protocol.Hash(UnmanagedFingerprints())) throw new HarnessException("post-qa", "An unmanaged object changed unexpectedly.");
            if (plan is not null) ExecutionCoordinator.ValidateOutcome(plan, DescribeOutcome(before, after, record));
        }
        catch (Exception ex)
        {
            try
            {
                if (_doc.CurrentUndoRecordSerialNumber != record) throw new HarnessException("undo-ownership", "Cannot compensate inside a record the adapter no longer owns.");
                ReplaceManaged(before);
                var recovered = Capture();
                if (!SameEntities(before, recovered) || Protocol.Hash(unmanaged) != Protocol.Hash(UnmanagedFingerprints()))
                    throw new HarnessException("compensation-qa", "Recovered objects do not match durable before-images.");
                failure = new HarnessException("apply-compensated", "Apply failed and its before-images were restored. Review the failed journal entry. Cause: " + ex.Message);
            }
            catch (Exception recovery)
            {
                failure = new HarnessException("failed-recovery", "Apply failed and compensation could not be verified. Stop editing and use the durable checkpoint. Apply: " + ex.Message + "; recovery: " + recovery.Message);
            }
        }
        finally
        {
            // Never invoke global Undo(), never close someone else's record.
            if (_doc.CurrentUndoRecordSerialNumber != record || !_doc.EndUndoRecord(record)) failure = new HarnessException("failed-recovery", "The owned Undo record could not be closed. Stop editing and inspect the checkpoint/journal.");
            _applying = false;
            ClearPreview();
        }
        if (failure is not null) throw failure;
        after ??= Capture();
        return DescribeOutcome(before, after, record);
    }

    private static ApplyOutcome DescribeOutcome(DocumentSnapshot before, DocumentSnapshot after, uint record)
    {
        var old = before.Entities.ToDictionary(x => x.RhinoId);
        var now = after.Entities.ToDictionary(x => x.RhinoId);
        return new(after, now.Keys.Except(old.Keys).ToArray(), now.Keys.Intersect(old.Keys).Where(x => now[x].Fingerprint != old[x].Fingerprint).ToArray(), old.Keys.Except(now.Keys).ToArray(), record, []);
    }

    private void ReplaceManaged(DocumentSnapshot target)
    {
        var wanted = target.Entities.ToDictionary(x => x.RhinoId);
        foreach (var obj in AllObjects().Where(x => !string.IsNullOrEmpty(x.Attributes.GetUserString(Protocol.EntityKey))).ToArray())
            if (!wanted.ContainsKey(obj.Id) && !_doc.Objects.Delete(obj.Id, true)) throw new HarnessException("restore-delete", $"Cannot delete managed object {obj.Id}.");
        foreach (var entity in target.Entities)
        {
            using var geometry = DeserializeGeometry(entity);
            using var attrs = DeserializeAttributes(entity);
            var live = _doc.Objects.FindId(entity.RhinoId);
            if (live is null)
            {
                var deleted = _doc.Objects.GetObjectList(new ObjectEnumeratorSettings { DeletedObjects = true, NormalObjects = true, HiddenObjects = true, LockedObjects = true }).FirstOrDefault(x => x.IsDeleted && x.Id == entity.RhinoId);
                if (deleted is not null && _doc.Objects.Undelete(deleted)) live = _doc.Objects.FindId(entity.RhinoId);
            }
            if (live is null)
            {
                if (_doc.Objects.Add(geometry, attrs) != entity.RhinoId) throw new HarnessException("restore-add", "Rhino could not restore the exact saved object GUID.");
            }
            else
            {
                if (string.IsNullOrEmpty(live.Attributes.GetUserString(Protocol.EntityKey))) throw new HarnessException("restore-collision", "Refusing to replace unmanaged object.");
                if (!_doc.Objects.Replace(entity.RhinoId, geometry, false) || !_doc.Objects.ModifyAttributes(entity.RhinoId, attrs, true))
                    throw new HarnessException("restore-replace", $"Could not restore entity {entity.EntityId}.");
            }
        }
        var actual = Capture();
        if (!SameEntities(target, actual)) throw new HarnessException("restore-qa", "Restored managed objects do not exactly match checkpoint fingerprints.");
    }

    private DocumentSnapshot ValidatePlan(ChangePlan plan)
    {
        var current = Capture();
        CheckExpected(plan.Request.Expected, current);
        if (plan.RequestHash != PlanValidator.Prepare(new(plan.Request, plan.Before, plan.RestoreTarget)).RequestHash || plan.Before.SnapshotHash != current.SnapshotHash)
            throw new HarnessException("plan-integrity", "Plan payload or detached before-state does not match the current document.");
        if (current.Issues.Length != 0) throw new HarnessException("qa-blocked", string.Join("\n", current.Issues));
        if (plan.Request.ToolId == "box.add")
        {
            if (string.IsNullOrWhiteSpace(plan.Request.EntityId) || current.Entities.Any(x => x.EntityId == plan.Request.EntityId))
                throw new HarnessException("identity-collision", "New EngineeringEntityId must be nonempty and unique.");
            var box = plan.Request.Box ?? throw new HarnessException("schema", "Box dimensions are required.");
            if (new[] {box.Width, box.Depth, box.Height}.Any(x => !double.IsFinite(x) || x <= current.Tolerance))
                throw new HarnessException("schema", "Box dimensions must be finite and greater than model tolerance.");
            CheckPoint(box.Origin);
        }
        else if (plan.Request.ToolId == "object.translate")
        {
            var entity = current.Entities.SingleOrDefault(x => x.RhinoId == plan.Request.ObjectId) ?? throw new HarnessException("managed-only", "Translation supports a single managed object.");
            var obj = _doc.Objects.FindId(entity.RhinoId);
            if (obj.IsLocked || _doc.Layers[obj.Attributes.LayerIndex].IsLocked || obj.IsReference) throw new HarnessException("object-locked", "The managed object is locked or referenced.");
            CheckPoint(plan.Request.Translation ?? throw new HarnessException("schema", "Translation is required."));
        }
        else if (plan.Request.ToolId == "checkpoint.restore" && plan.RestoreTarget is not null) { }
        else throw new HarnessException("unsupported-tool", "Stage 1 supports only box.add and object.translate; split/join lineage is not modeled.");
        return current;
    }

    private Brep BuildResultGeometry(ChangePlan plan)
    {
        if (plan.Request.ToolId == "box.add")
        {
            var b = plan.Request.Box!;
            return new Box(new Plane(new Point3d(b.Origin.X, b.Origin.Y, b.Origin.Z), Vector3d.ZAxis), new Interval(0, b.Width), new Interval(0, b.Depth), new Interval(0, b.Height)).ToBrep();
        }
        var source = plan.Before.Entities.Single(x => x.RhinoId == plan.Request.ObjectId);
        var geometry = DeserializeGeometry(source);
        var t = plan.Request.Translation!;
        if (!geometry.Transform(Transform.Translation(t.X, t.Y, t.Z)) || !geometry.IsValid)
        { geometry.Dispose(); throw new HarnessException("geometry-invalid", "Detached translation failed."); }
        return geometry;
    }
    private static void CheckPoint(Point3 p)
    {
        if (!double.IsFinite(p.X) || !double.IsFinite(p.Y) || !double.IsFinite(p.Z)) throw new HarnessException("schema", "Coordinates must be finite.");
    }
    private static void CheckExpected(ExpectedContext expected, DocumentSnapshot current)
    {
        if (expected.DocumentId != current.DocumentId || expected.SessionId != current.SessionId || expected.Revision != current.Revision || expected.SnapshotHash != current.SnapshotHash)
            throw new HarnessException("stale-context", "Document/session/revision/fingerprint changed. Prepare a new preview.");
    }
    private static bool SameEntities(DocumentSnapshot a, DocumentSnapshot b) =>
        Protocol.Hash(a.Entities.OrderBy(x => x.RhinoId).ToArray()) == Protocol.Hash(b.Entities.OrderBy(x => x.RhinoId).ToArray());
    private static Brep DeserializeGeometry(EntitySnapshot entity)
    {
        var value = CommonObject.FromJSON(entity.GeometryJson);
        if (value is Brep brep && brep.IsValid) return brep;
        value?.Dispose(); throw new HarnessException("serialization", "Checkpoint contains unsupported or invalid geometry.");
    }
    private sealed record AttributeEnvelope(string RhinoJson, Guid LayerId, string LayerHash, Guid? MaterialId, string? MaterialHash);
    private string LineageFile => Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "RhinoAi", "executor", _documentId.ToString("D"), "lineage-block.txt");
    private static AttributeEnvelope ReadEnvelope(EntitySnapshot entity) => JsonSerializer.Deserialize<AttributeEnvelope>(entity.AttributesJson, Protocol.Json) ?? throw new HarnessException("serialization", "Attribute reference envelope is missing.");
    private static ObjectAttributes DeserializeAttributes(EntitySnapshot entity)
    {
        var value = CommonObject.FromJSON(ReadEnvelope(entity).RhinoJson);
        if (value is ObjectAttributes attrs && attrs.ObjectId == entity.RhinoId && attrs.GetUserString(Protocol.EntityKey) == entity.EntityId) return attrs;
        value?.Dispose(); throw new HarnessException("serialization", "Checkpoint attributes/identity do not match saved entity.");
    }
    private void ValidateAttributeReferences(ObjectAttributes attrs, AttributeEnvelope refs)
    {
        if (attrs.LayerIndex < 0 || attrs.LayerIndex >= _doc.Layers.Count || _doc.Layers[attrs.LayerIndex].IsDeleted)
            throw new HarnessException("restore-layer", "Checkpoint layer no longer exists. Managed-scope restore does not reconstruct layer/material tables.");
        if (_doc.Layers[attrs.LayerIndex].Id != refs.LayerId || Protocol.Hash(_doc.Layers[attrs.LayerIndex].ToJSON(Serialization)) != refs.LayerHash)
            throw new HarnessException("restore-layer", "Checkpoint layer identity or properties have changed. This scope cannot restore layer tables.");
        if (attrs.MaterialIndex >= _doc.Materials.Count) throw new HarnessException("restore-material", "Checkpoint material reference is no longer valid.");
        var materialIndex = attrs.MaterialSource == ObjectMaterialSource.MaterialFromLayer ? _doc.Layers[attrs.LayerIndex].RenderMaterialIndex : attrs.MaterialIndex;
        if (refs.MaterialId is not null && (materialIndex < 0 || materialIndex >= _doc.Materials.Count || _doc.Materials[materialIndex].Id != refs.MaterialId || Protocol.Hash(_doc.Materials[materialIndex].ToJSON(Serialization)) != refs.MaterialHash))
            throw new HarnessException("restore-material", "Checkpoint material identity or properties changed. This scope cannot restore material tables.");
    }
    private EntitySnapshot Snapshot(RhinoObject obj)
    {
        var geometryJson = obj.Geometry.ToJSON(Serialization);
        var layer = _doc.Layers[obj.Attributes.LayerIndex];
        var materialIndex = obj.Attributes.MaterialSource == ObjectMaterialSource.MaterialFromLayer ? layer.RenderMaterialIndex : obj.Attributes.MaterialIndex;
        var material = materialIndex >= 0 && materialIndex < _doc.Materials.Count ? _doc.Materials[materialIndex] : null;
        var envelope = new AttributeEnvelope(obj.Attributes.ToJSON(Serialization), layer.Id, Protocol.Hash(layer.ToJSON(Serialization)), material?.Id, material is null ? null : Protocol.Hash(material.ToJSON(Serialization)));
        var attributesJson = JsonSerializer.Serialize(envelope, Protocol.Json);
        var valid = obj.Geometry is Brep brep && brep.IsValid && brep.IsSolid && brep.Faces.Count == 6 && brep.Vertices.Count == 8 && obj.Attributes.GetUserString(KindKey) == "box";
        using var semanticAttributes = obj.Attributes.Duplicate();
        semanticAttributes.ObjectId = Guid.Empty;
        var semantics = semanticAttributes.ToJSON(Serialization);
        return new(obj.Id, obj.Attributes.GetUserString(Protocol.EntityKey)!, Protocol.Hash(new { geometryJson, semantics, envelope.LayerId, envelope.LayerHash, envelope.MaterialId, envelope.MaterialHash }), geometryJson, attributesJson, "Brep", valid);
    }
    private RhinoObject[] AllObjects() => _doc.Objects.GetObjectList(new ObjectEnumeratorSettings
        { NormalObjects = true, HiddenObjects = true, LockedObjects = true, ActiveObjects = true, ReferenceObjects = true, DeletedObjects = false, IdefObjects = false }).ToArray();
    private SortedDictionary<Guid, string> UnmanagedFingerprints() => new(AllObjects().Where(x => string.IsNullOrEmpty(x.Attributes.GetUserString(Protocol.EntityKey)))
        .ToDictionary(x => x.Id, x => Protocol.Hash(new { Geometry = x.Geometry.ToJSON(Serialization), Attributes = x.Attributes.ToJSON(Serialization) })));
    private void EnsureOpen()
    {
        RhinoUiDispatcher.RequireUiThread();
        if (_closed || RhinoDoc.FromRuntimeSerialNumber(RuntimeSerial) is null) throw new HarnessException("document-closed", "The document session has closed.");
        if (RhinoDoc.ActiveDoc?.RuntimeSerialNumber != RuntimeSerial) throw new HarnessException("document-inactive", "Switch back to the document bound to this panel.");
    }
    private void BumpRevision() { _revision = Math.Max(_revision + 1, DateTime.UtcNow.Ticks); _dirty = true; _previewInvalid = true; }
    private void ObjectChanged(object? sender, RhinoObjectEventArgs e) { BumpRevision(); }
    private void ObjectReplaced(object? sender, RhinoReplaceObjectEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void AttributesChanged(object? sender, RhinoModifyObjectAttributesEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void LayerChanged(object? sender, LayerTableEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void MaterialChanged(object? sender, MaterialTableEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void LinetypeChanged(object? sender, LinetypeTableEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void GroupChanged(object? sender, GroupTableEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void DocumentChanged(object? sender, DocumentEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) BumpRevision(); }
    private void DocumentClosed(object? sender, DocumentEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) { _closed = true; BumpRevision(); } }
    private void DocumentOpening(object? sender, DocumentOpenEventArgs e) { if (e.Document.RuntimeSerialNumber == RuntimeSerial) { if (!e.Merge && !e.Reference) _closed = true; BumpRevision(); } }
    private void ActiveDocumentChanged(object? sender, DocumentEventArgs e) { BumpRevision(); }
    private void UndoRedo(object? sender, UndoRedoEventArgs e) { if (e.IsBeginUndo || e.IsBeginRedo || e.IsEndUndo || e.IsEndRedo) BumpRevision(); }
    private void BeginCommand(object? sender, CommandEventArgs e)
    {
        if (e.DocumentRuntimeSerialNumber != RuntimeSerial || _applying || !_lineageCommands.Contains(e.CommandEnglishName)) return;
        // Read geometry only on the UI thread, outside notification mutation. No attributes are written here.
        if (RhinoApp.InvokeRequired) { _unsafeLineage = "A topology command ran off the expected UI thread. Reconciliation is required."; BumpRevision(); return; }
        _observedCommand = e.CommandEnglishName;
        _commandBeforeHash = Protocol.Hash(AllObjects().Where(x => !string.IsNullOrEmpty(x.Attributes.GetUserString(Protocol.EntityKey))).Select(Snapshot).OrderBy(x => x.RhinoId).ToArray());
    }
    private void EndCommand(object? sender, CommandEventArgs e)
    {
        if (e.DocumentRuntimeSerialNumber != RuntimeSerial || e.CommandEnglishName != _observedCommand) return;
        if (RhinoApp.InvokeRequired) { _unsafeLineage = "Topology completion arrived outside the Rhino UI thread. Manual reconciliation is required."; BumpRevision(); return; }
        var current = Protocol.Hash(AllObjects().Where(x => !string.IsNullOrEmpty(x.Attributes.GetUserString(Protocol.EntityKey))).Select(Snapshot).OrderBy(x => x.RhinoId).ToArray());
        if (_commandBeforeHash != current)
        {
            _unsafeLineage = $"Unmodeled {_observedCommand} changed managed entities. Automatic lineage recovery is unavailable. Stop agent edits and obtain explicit manual geometry/identity reconciliation; normal checkpoint Restore is blocked while QA is unresolved.";
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(LineageFile)!);
                using var stream = new FileStream(LineageFile, FileMode.Create, FileAccess.Write, FileShare.Read, 4096, FileOptions.WriteThrough);
                var bytes = System.Text.Encoding.UTF8.GetBytes(_unsafeLineage); stream.Write(bytes); stream.Flush(true);
            }
            catch (IOException) { _unsafeLineage += " Durable lineage marker could not be saved. Do not save/reopen as a recovery workaround."; }
        }
        _observedCommand = null; _commandBeforeHash = null; BumpRevision();
    }
    private void OnIdle(object? sender, EventArgs e)
    {
        if (!_dirty || _applying) return;
        if (_previewInvalid) ClearPreview();
        _dirty = false;
        Invalidated?.Invoke(this, EventArgs.Empty);
    }
    public void Dispose()
    {
        RhinoUiDispatcher.RequireUiThread(); ClearPreview();
        RhinoDoc.AddRhinoObject -= ObjectChanged; RhinoDoc.DeleteRhinoObject -= ObjectChanged; RhinoDoc.UndeleteRhinoObject -= ObjectChanged;
        RhinoDoc.ReplaceRhinoObject -= ObjectReplaced; RhinoDoc.ModifyObjectAttributes -= AttributesChanged;
        RhinoDoc.LinetypeTableEvent -= LinetypeChanged; RhinoDoc.GroupTableEvent -= GroupChanged;
        RhinoDoc.LayerTableEvent -= LayerChanged; RhinoDoc.MaterialTableEvent -= MaterialChanged;
        RhinoDoc.DocumentPropertiesChanged -= DocumentChanged; RhinoDoc.CloseDocument -= DocumentClosed;
        RhinoDoc.BeginOpenDocument -= DocumentOpening; RhinoDoc.EndOpenDocument -= DocumentOpening; RhinoDoc.ActiveDocumentChanged -= ActiveDocumentChanged;
        Command.UndoRedo -= UndoRedo; Command.BeginCommand -= BeginCommand; Command.EndCommand -= EndCommand; RhinoApp.Idle -= OnIdle;
    }
}
