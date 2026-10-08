namespace RhinoAi.Contracts;

/// <summary>Versioned, single-decision planning. A plan is never permission to mutate Rhino.</summary>
public static class PlanningProtocol
{
    public const int Version = 2;
    public static string ContextHash(ExpectedContext expected, Guid[] selectedObjectIds) =>
        Protocol.Hash(new { Expected = expected, SelectedObjectIds = selectedObjectIds.OrderBy(x => x).ToArray() });
}

/// <summary>Only values explicitly entered/reviewed by the user belong in Inputs; UI defaults must not populate it.</summary>
public sealed record PlannerInputs(BoxSpec? Box = null, string? EntityId = null, Point3? Translation = null, CladdingReviewRequest? Cladding = null);
public sealed record PlannerRequest(int PlannerVersion, Guid TaskId, Guid OperationId, string Prompt,
    ExpectedContext Expected, DocumentSnapshot Snapshot, Guid[] SelectedObjectIds, PlannerInputs? Inputs = null);
public sealed record PlannedTool(string ToolId, BoxSpec? Box = null, string? EntityId = null, Guid? ObjectId = null, Point3? Translation = null);
/// <summary>Kind is exactly clarification, tool, or cladding.review. At most one supported tool is permitted.</summary>
public sealed record PlannerDecision(string Kind, string? Message = null, PlannedTool? Tool = null);
public sealed record PlannerValidationRequest(PlannerRequest Request, PlannerDecision Decision);
public sealed record PlannerResponse(int PlannerVersion, string Status, string Message, string ContextHash,
    PlannerDecision? Decision = null, ChangePlan? Plan = null, CladdingReviewRequest? CladdingRequest = null);
