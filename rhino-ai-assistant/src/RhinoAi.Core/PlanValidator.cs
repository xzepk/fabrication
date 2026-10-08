using RhinoAi.Contracts;
using System.Text.RegularExpressions;
using System.Diagnostics.CodeAnalysis;
namespace RhinoAi.Core;

public static partial class PlanValidator
{
    public const int MaxObjects = 10000;
    public static ChangePlan Prepare(PrepareRequest input)
    {
        if (input is null || input.Request is null || input.Snapshot is null) Fail("invalid-payload", "Request and snapshot are required.");
        var r = input!.Request;
        if (r.Expected is null) Fail("invalid-context", "Expected context is required.");
        var s = input.Snapshot;
        if (r.ProtocolVersion != Protocol.Version) Fail("protocol-version", "Unsupported protocol version.");
        if (r.TaskId == Guid.Empty || r.OperationId == Guid.Empty) Fail("invalid-id", "Task and operation IDs are required.");
        ValidateSnapshot(s);
        Match(r.Expected, s);
        switch (r.ToolId)
        {
            case "box.add":
                if (r.Box is null || r.ObjectId is not null || r.Translation is not null || r.CheckpointId is not null || input.RestoreTarget is not null) Fail("invalid-arguments", "box.add accepts only Box and EntityId.");
                ValidateBox(r.Box!);
                if (s.Entities.Length >= MaxObjects) Fail("object-limit", "Adding an object would exceed the managed-object limit.");
                if (Math.Min(r.Box!.Width, Math.Min(r.Box.Depth, r.Box.Height)) <= s.Tolerance) Fail("below-tolerance", "Box dimensions must exceed document tolerance.");
                ValidateEntityId(r.EntityId);
                if (s.Entities.Any(e => e.EntityId == r.EntityId)) Fail("identity-collision", "Entity ID already exists.");
                return new(r, Protocol.Hash(r), s, $"Add one box ({r.EntityId}); units: {s.Units}", ["REVIEW only. No production approval."]);
            case "object.translate":
                if (r.ObjectId is null || r.Translation is null || r.Box is not null || r.EntityId is not null || r.CheckpointId is not null || input.RestoreTarget is not null) Fail("invalid-arguments", "object.translate requires ObjectId and Translation only.");
                ValidatePoint(r.Translation!);
                if (r.Translation is { X: 0, Y: 0, Z: 0 }) Fail("empty-change", "Zero translation has no effect.");
                if (!s.Entities.Any(e => e.RhinoId == r.ObjectId)) Fail("unsupported-object", "Target must be a supported managed object in this snapshot.");
                return new(r, Protocol.Hash(r), s, $"Translate one managed object; units: {s.Units}", ["REVIEW only. No production approval."]);
            case "checkpoint.restore":
                var target = input.RestoreTarget;
                if (r.CheckpointId is null || target is null || r.CheckpointId != target.CheckpointId || target.DocumentId != s.DocumentId || target.Snapshot.DocumentId != s.DocumentId || target.Scope != "managed-objects" || r.Box is not null || r.ObjectId is not null || r.Translation is not null || r.EntityId is not null) Fail("invalid-restore", "A matching managed-scope checkpoint from this document is required.");
                ValidateSnapshot(target!.Snapshot);
                if (target.Snapshot.Units != s.Units || target.Snapshot.Tolerance != s.Tolerance) Fail("restore-units", "Checkpoint units and tolerance must match the current document.");
                return new(r, Protocol.Hash(new { Request = r, Target = target }), s, $"Restore {target.Snapshot.Entities.Length} managed objects. Replace ALL later managed-object edits; unmanaged objects are preserved.", ["Explicit acceptance required. Later managed-object edits will be replaced. A pre-restore safety checkpoint is recorded."], target);
            default: throw new HarnessException("unsupported-tool", "This tool is not available in the foundational slice.");
        }
    }
    public static void ValidateSnapshot(DocumentSnapshot s)
    {
        if (s is null) Fail("invalid-context", "Snapshot is required.");
        if (s!.DocumentId == Guid.Empty || s.SessionId == Guid.Empty || s.Revision < 0) Fail("invalid-context", "Document/session IDs and revision are required.");
        if (!new[] { "Millimeters", "Centimeters", "Meters", "Inches", "Feet" }.Contains(s.Units)) Fail("unsupported-units", "Supported explicit length units are required.");
        if (!double.IsFinite(s.Tolerance) || s.Tolerance <= 0 || s.Tolerance > 1) Fail("invalid-tolerance", "Tolerance must be finite and in (0, 1] document units.");
        if (s.Issues is null || s.Issues.Length != 0) Fail("model-qa", "Resolve document QA issues before planning or applying.");
        if (s.Entities is null || s.Entities.Length > MaxObjects) Fail("object-limit", "Managed object limit exceeded.");
        if (s.Entities!.Any(e => e is null || e.RhinoId == Guid.Empty || !e.IsValid || string.IsNullOrWhiteSpace(e.Fingerprint) || string.IsNullOrWhiteSpace(e.GeometryJson) || string.IsNullOrWhiteSpace(e.AttributesJson))) Fail("invalid-geometry", "Managed entities need valid detached geometry, attributes and fingerprints.");
        foreach (var e in s.Entities) ValidateEntityId(e.EntityId);
        if (s.Entities.Select(e => e.RhinoId).Distinct().Count() != s.Entities.Length || s.Entities.Select(e => e.EntityId).Distinct(StringComparer.Ordinal).Count() != s.Entities.Length) Fail("identity-collision", "Duplicate Rhino or engineering IDs require explicit reconciliation.");
    }
    public static void Match(ExpectedContext expected, DocumentSnapshot actual)
    {
        if (expected.DocumentId != actual.DocumentId || expected.SessionId != actual.SessionId || expected.Revision != actual.Revision || expected.SnapshotHash != actual.SnapshotHash) Fail("stale-context", "The document, session or model has changed. Prepare a new preview.");
    }
    public static ExpectedContext Expected(DocumentSnapshot s) => new(s.DocumentId, s.SessionId, s.Revision, s.SnapshotHash);
    public static void ValidateBox(BoxSpec b)
    {
        ValidatePoint(b.Origin);
        if (!double.IsFinite(b.Width) || !double.IsFinite(b.Depth) || !double.IsFinite(b.Height) || b.Width <= 0 || b.Depth <= 0 || b.Height <= 0 || b.Width > 1e7 || b.Depth > 1e7 || b.Height > 1e7) Fail("invalid-geometry", "Box dimensions must be finite, positive and no larger than 1e7 document units.");
    }
    private static void ValidatePoint(Point3 p)
    {
        if (p is null || !double.IsFinite(p.X) || !double.IsFinite(p.Y) || !double.IsFinite(p.Z) || Math.Abs(p.X) > 1e8 || Math.Abs(p.Y) > 1e8 || Math.Abs(p.Z) > 1e8) Fail("invalid-coordinate", "Coordinates must be finite and bounded.");
    }
    private static void ValidateEntityId(string? id) { if (id is null || !EntityPattern().IsMatch(id)) Fail("invalid-entity-id", "Use a unique ASCII engineering ID (1–128 letters/digits/dot/underscore/colon/hyphen)."); }
    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", RegexOptions.CultureInvariant)] private static partial Regex EntityPattern();
    [DoesNotReturn]
    private static void Fail(string code, string message) => throw new HarnessException(code, message);
}
