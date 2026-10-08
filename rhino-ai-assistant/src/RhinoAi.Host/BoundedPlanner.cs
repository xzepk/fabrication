using System.Text.Json;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Host;

/// <summary>One model turn, one decision. Neither planning nor external candidate validation writes a journal or document.</summary>
public sealed class BoundedPlanner(LocalChatCompletionClient client)
{
    public async Task<PlannerResponse> PlanAsync(PlannerRequest request, CancellationToken ct)
    {
        ValidateRequest(request);
        if (client.Status != "READY") return Reply(request, client.Status,
            client.Status == "NOT_CONFIGURED" ? "No local model is configured. Structured tools remain available." : "Local model configuration is invalid. Use the documented literal loopback endpoint and model name.");
        var facts = PlannerPromptFacts.Resolve(request);
        var content = await client.CompleteAsync(request, facts, ct);
        PlannerDecision decision;
        try { decision = StrictJson.Parse<PlannerDecision>(content); }
        catch (JsonException) { throw new HostHttpException(502, "invalid_model_decision", "The local model returned malformed, duplicate, missing or unknown decision fields. No action was prepared."); }
        return Validate(request, decision);
    }

    public static void ValidateRequest(PlannerRequest request)
    {
        if (request is null || request.Expected is null || request.Snapshot is null || request.SelectedObjectIds is null)
            throw new HarnessException("planner-request", "Expected context, snapshot and selected IDs are required.");
        if (request.PlannerVersion != PlanningProtocol.Version) throw new HarnessException("planner-version", "Unsupported planner contract version.");
        if (request.TaskId == Guid.Empty || request.OperationId == Guid.Empty) throw new HarnessException("planner-id", "Task and operation IDs are required.");
        if (string.IsNullOrWhiteSpace(request.Prompt) || request.Prompt.Length > LocalModelSettings.MaximumPromptChars)
            throw new HarnessException("planner-prompt-limit", "Use a nonempty prompt no longer than 4096 characters.");
        PlanValidator.ValidateSnapshot(request.Snapshot);
        PlanValidator.Match(request.Expected, request.Snapshot);
        if (request.Snapshot.Entities.Length > LocalModelSettings.MaximumContextObjects)
            throw new HarnessException("planner-context-limit", "This planner supports at most 64 managed objects in its read-only context.");
        if (request.SelectedObjectIds.Length > LocalModelSettings.MaximumSelectedObjects ||
            request.SelectedObjectIds.Distinct().Count() != request.SelectedObjectIds.Length ||
            request.SelectedObjectIds.Any(id => id == Guid.Empty || !request.Snapshot.Entities.Any(e => e.RhinoId == id)))
            throw new HarnessException("planner-selection", "Selection must contain at most 16 distinct supported managed objects from this snapshot.");
        // Validate client-supplied facts too, even if the model eventually chooses clarification.
        if (request.Inputs?.Box is not null) PlanValidator.ValidateBox(request.Inputs.Box);
        if (request.Inputs?.Translation is Point3 t && (!double.IsFinite(t.X) || !double.IsFinite(t.Y) || !double.IsFinite(t.Z)))
            throw new HarnessException("planner-input", "Translation must be finite.");
        if (request.Inputs?.EntityId is string idText && (idText.Length > 128 || idText.Length == 0))
            throw new HarnessException("planner-input", "Engineering ID must be between 1 and 128 characters.");
    }

    public static PlannerResponse Validate(PlannerRequest request, PlannerDecision decision)
    {
        ValidateRequest(request);
        if (decision is null || decision.Kind is not ("clarification" or "tool" or "cladding.review") || decision.Message?.Length > 1024)
            throw new HarnessException("planner-decision", "Only one bounded clarification, tool or cladding.review decision is supported.");
        if (decision.Kind == "clarification")
        {
            if (decision.Tool is not null || string.IsNullOrWhiteSpace(decision.Message)) throw new HarnessException("planner-decision", "Clarification requires a question and cannot contain a tool.");
            return Reply(request, "clarification", decision.Message, decision);
        }
        if (decision.Kind == "cladding.review")
        {
            if (decision.Tool is not null) throw new HarnessException("planner-decision", "A Skill decision cannot contain a tool.");
            var cladding = request.Inputs?.Cladding;
            if (cladding is null) return Clarify(request, "Provide and review the plate dimensions, origins, materials, grades, densities, source entities and requested outputs before cladding review.");
            if (cladding.Expected is null || cladding.Snapshot is null || cladding.SelectedEntityIds is null)
                throw new HarnessException("planner-cladding-context", "Cladding proposal requires complete bound context and source selection.");
            PlanValidator.Match(cladding.Expected, request.Snapshot);
            if (cladding.Snapshot.SnapshotHash != request.Snapshot.SnapshotHash)
                throw new HarnessException("planner-cladding-context", "Cladding proposal must use this exact planning snapshot.");
            var selectedEntityIds = request.Snapshot.Entities.Where(e => request.SelectedObjectIds.Contains(e.RhinoId)).Select(e => e.EntityId).OrderBy(x => x, StringComparer.Ordinal);
            if (!selectedEntityIds.SequenceEqual(cladding.SelectedEntityIds.OrderBy(x => x, StringComparer.Ordinal)))
                throw new HarnessException("planner-cladding-selection", "Cladding proposal must use the exact selected managed entities.");
            try { CladdingReviewValidator.Validate(cladding); }
            catch (HarnessException error)
            {
                var question = MissingCladdingQuestion(cladding, error.Code);
                if (question is null) throw;
                return Clarify(request, question);
            }
            return Reply(request, "cladding.review", "Typed cladding REVIEW proposal. Explicit review execution and later geometry preview acceptance are separate steps.", decision, cladding: cladding);
        }
        if (decision.Tool is not PlannedTool tool) throw new HarnessException("planner-decision", "Tool decision requires exactly one supported tool.");
        var facts = PlannerPromptFacts.Resolve(request);
        ToolRequest action;
        switch (tool.ToolId)
        {
            case "box.add":
                if (tool.ObjectId is not null || tool.Translation is not null) throw new HarnessException("planner-arguments", "box.add accepts only box and entityId.");
                if (facts.Box is null || string.IsNullOrWhiteSpace(facts.EntityId))
                    return Clarify(request, "Specify width, depth, height, origin and engineering ID in document units. Use explicit fields or width=100; depth=100; height=100; origin=(0,0,0); entityId=BOX-001. Values are examples, not defaults.");
                if (tool.Box != facts.Box || tool.EntityId != facts.EntityId)
                    throw new HarnessException("planner-ungrounded", "Model box arguments must exactly match the explicit user inputs; no dimensions, origin or ID may be invented.");
                action = new(Protocol.Version, request.TaskId, request.OperationId, tool.ToolId, request.Expected, tool.Box, EntityId: tool.EntityId);
                break;
            case "object.translate":
                if (tool.Box is not null || tool.EntityId is not null) throw new HarnessException("planner-arguments", "object.translate accepts only objectId and translation.");
                if (request.SelectedObjectIds.Length != 1 || facts.Translation is null)
                    return Clarify(request, "Select exactly one supported managed object and specify a translation vector in document units, using explicit fields or translation=(100,0,0). Values are examples, not defaults.");
                if (tool.ObjectId != request.SelectedObjectIds[0] || tool.Translation != facts.Translation)
                    throw new HarnessException("planner-ungrounded", "Model target and translation must exactly match the current selected object and explicit user input.");
                action = new(Protocol.Version, request.TaskId, request.OperationId, tool.ToolId, request.Expected, ObjectId: tool.ObjectId, Translation: tool.Translation);
                break;
            default: throw new HarnessException("planner-tool", "Only box.add and object.translate are available to this bounded planner.");
        }
        var plan = PlanValidator.Prepare(new(action, request.Snapshot));
        return Reply(request, "tool", "Validated proposal only. Create a current detached preview, then explicitly accept it before any Rhino mutation.", decision, plan);
    }

    // Convert only unambiguously absent authoring inputs to questions. Actual Skill validation remains strict.
    private static string? MissingCladdingQuestion(CladdingReviewRequest request, string code)
    {
        if (request.SourceMode is not ("explicit_design" or "selected_managed") || request.Components is null ||
            request.Components.Any(c => c is null) || request.Sources is null || request.Sources.Any(s => s is null) ||
            request.Targets is null || request.Targets.Any(t => !CladdingReviewValidator.RequiredTargets.Contains(t, StringComparer.Ordinal)) ||
            request.Targets.Distinct(StringComparer.Ordinal).Count() != request.Targets.Length) return null;
        // Never turn malformed, negative/nonfinite values or explicitly unsupported geometry into missing-data questions.
        foreach (var c in request.Components)
        {
            if (c.OriginMM is null || c.SourceEntityIds is null || c.Quantity != 1 || c.GeometryType != "planar_plate" ||
                c.Plane is not ("XY" or "XZ" or "YZ") || c.Features is { Length: > 0 } ||
                new[] { c.WidthMM, c.HeightMM, c.ThicknessMM, c.DensityKgM3 }.Any(v => !double.IsFinite(v) || v < 0) ||
                new[] { c.OriginMM.X, c.OriginMM.Y, c.OriginMM.Z }.Any(v => !double.IsFinite(v) || Math.Abs(v) > 10000000) ||
                new[] { c.WidthMM, c.HeightMM, c.ThicknessMM }.Any(v => v > 100000) || c.DensityKgM3 > 30000 ||
                new[] { c.Material, c.Grade, c.DisplayLabel }.Any(v => v is not null && (v.Length > 128 || v.Any(char.IsControl))) ||
                c.Measurements is { } measurements && measurements.Any(m => m is null || !double.IsFinite(m.DesignValueMM) || !double.IsFinite(m.MeasuredValueMM) || !double.IsFinite(m.UsedValueMM) || m.DesignValueMM <= 0 || m.MeasuredValueMM <= 0 || m.UsedValueMM <= 0)) return null;
        }
        return code switch
        {
            "cladding-text" when request.Components.Any(c => string.IsNullOrWhiteSpace(c.Material)) => "Which material should each plate use? Enter the material explicitly before cladding review.",
            "cladding-text" when request.Components.Any(c => string.IsNullOrWhiteSpace(c.Grade)) => "Which material grade should each plate use? Enter the grade explicitly before cladding review.",
            "cladding-density" when request.Components.Any(c => c.DensityKgM3 == 0) => "What material density in kg/m3 should each plate use for its theoretical mass? Enter it explicitly.",
            "cladding-geometry" when request.Components.Any(c => c.WidthMM == 0 || c.HeightMM == 0 || c.ThicknessMM == 0) => "What are each plate's width, height and thickness in millimetres? Supply every missing dimension explicitly.",
            "cladding-targets" when request.Targets.Length < CladdingReviewValidator.RequiredTargets.Length => "Which review outputs do you want? This adapter requires explicit step, drawings, bom and nesting targets; confirm all four before review.",
            "cladding-sources" when request.SourceMode == "selected_managed" && request.SelectedEntityIds.Length == 0 && request.Sources.Length == 0 => "Which managed objects should become plates? Select the supported source boxes in Rhino and capture their current geometry before review.",
            _ => null
        };
    }

    private static PlannerResponse Clarify(PlannerRequest request, string message) => Reply(request, "clarification", message, new("clarification", message));
    private static PlannerResponse Reply(PlannerRequest request, string status, string message, PlannerDecision? decision = null, ChangePlan? plan = null, CladdingReviewRequest? cladding = null) =>
        new(PlanningProtocol.Version, status, message, PlanningProtocol.ContextHash(request.Expected, request.SelectedObjectIds), decision, plan, cladding);
}
