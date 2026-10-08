using System.Text.RegularExpressions;
using RhinoAi.Contracts;
using RhinoAi.Core;

namespace RhinoAi.Host;

/// <summary>Domain input checks before any subprocess. Selected geometry is an explicit UI-thread attestation,
/// never inferred by the Host from the opaque Rhino serialization or from an LLM answer.</summary>
public static partial class CladdingReviewValidator
{
    public const int MaximumPlates = 128;
    public static readonly string[] RequiredTargets = ["step", "drawings", "bom", "nesting"];
    public static void Validate(CladdingReviewRequest r)
    {
        Need(r is not null && r.Expected is not null && r.Snapshot is not null, "required-field", "A complete review request and document snapshot are required.");
        PlanValidator.ValidateSnapshot(r!.Snapshot);
        PlanValidator.Match(r.Expected, r.Snapshot);
        Need(r.ProtocolVersion == Protocol.Version && r.JobId != Guid.Empty, "invalid-job", "A supported protocol and nonempty review job UUID are required.");
        Need(r.Snapshot.Units == "Millimeters", "cladding-units", "This plate bridge supports explicit millimetre documents only.");
        Need(r.Components is { Length: >= 1 and <= MaximumPlates } && r.Components.All(x => x is not null), "plate-limit", "Supply between 1 and 128 explicit plates.");
        Need(r.Targets is not null && r.Targets.Length == RequiredTargets.Length && r.Targets.ToHashSet(StringComparer.Ordinal).SetEquals(RequiredTargets), "cladding-targets", "All review targets step, drawings, bom and nesting are required.");
        Need(r.SelectedEntityIds is { Length: <= MaximumPlates } && r.Sources is { Length: <= MaximumPlates } && r.Sources.All(x => x is not null), "cladding-sources", "Explicit bounded selection and source arrays are required.");
        Need(r.SourceMode is "explicit_design" or "selected_managed", "cladding-source-mode", "Use explicit_design or selected_managed; arbitrary drawing interpretation is unsupported.");
        var sourceIds = r.SelectedEntityIds!.ToHashSet(StringComparer.Ordinal);
        Need(sourceIds.Count == r.SelectedEntityIds.Length, "identity-collision", "Selected source IDs must be unique.");
        if (r.SourceMode == "explicit_design") Need(sourceIds.Count == 0 && r.Sources!.Length == 0, "cladding-sources", "Explicit design has no implied Rhino source selection.");
        else
        {
            Need(sourceIds.Count > 0 && r.Sources!.Length == sourceIds.Count && sourceIds.SetEquals(r.Sources.Select(x => x.EntityId)), "cladding-sources", "Every selected managed entity needs one exact rectangular source attestation.");
            foreach (var source in r.Sources!)
            {
                var entity = r.Snapshot.Entities.SingleOrDefault(x => x.EntityId == source.EntityId);
                Need(entity is not null && entity.IsValid && entity.Kind == "Brep" && source.Fingerprint == entity.Fingerprint, "cladding-source-stale", "Selected source fingerprint must match the immutable managed snapshot.");
                ValidateBox(source.BoxMM, r.Snapshot.Tolerance);
            }
        }
        var ids = new HashSet<string>(r.Snapshot.Entities.Select(x => x.EntityId), StringComparer.OrdinalIgnoreCase);
        var usedSources = new HashSet<string>(StringComparer.Ordinal);
        foreach (var component in r.Components!)
        {
            Need(component.EntityId is not null && EntityIdPattern().IsMatch(component.EntityId) && ids.Add(component.EntityId), "identity-collision", "Each output needs a new unique portable engineering ID, including case-insensitive uniqueness.");
            Text(component.DisplayLabel, "DisplayLabel"); Text(component.Material, "Material"); Text(component.Grade, "Grade");
            Need(component.GeometryType == "planar_plate" && (component.Features is null || component.Features.Length == 0), "unsupported-cladding-feature", "Only rectangular unbent, unperforated planar plates are supported. Other features may not be dropped.");
            Need(component.Plane is "XY" or "XZ" or "YZ", "cladding-plane", "Only axis-aligned XY, XZ and YZ plate orientations are supported.");
            ValidateBox(Box(component), r.Snapshot.Tolerance);
            Need(component.ThicknessMM <= Math.Min(component.WidthMM, component.HeightMM), "cladding-thickness", "Thickness must not exceed the blank width or height.");
            Need(double.IsFinite(component.DensityKgM3) && component.DensityKgM3 is > 0 and <= 30000, "cladding-density", "Explicit finite material density in (0, 30000] kg/m3 is required.");
            Need(component.Quantity == 1, "cladding-quantity", "Use one explicit component ID and origin for every plate instance; quantity must be 1.");
            Need(component.SourceEntityIds is not null, "cladding-sources", "Source entity IDs must be supplied explicitly.");
            if (r.SourceMode == "explicit_design") Need(component.SourceEntityIds!.Length == 0, "cladding-sources", "Explicit design cannot claim uncaptured source geometry.");
            else
            {
                Need(component.SourceEntityIds!.Length == 1 && sourceIds.Contains(component.SourceEntityIds[0]) && usedSources.Add(component.SourceEntityIds[0]), "cladding-sources", "Each selected source maps to exactly one plate; panelization is not implemented.");
                var source = r.Sources!.Single(x => x.EntityId == component.SourceEntityIds[0]);
                Need(source.BoxMM == DesignBox(component), "cladding-source-mismatch", "Plate origin and original design dimensions must match the selected rectangular source. Changed dimensions require explicit design/measured/used adoption records.");
            }
            if (component.Measurements is not null)
            {
                Need(component.Measurements.Length <= 3 && component.Measurements.All(x => x is not null) && component.Measurements.Select(x => x.Field).Distinct(StringComparer.Ordinal).Count() == component.Measurements.Length, "cladding-measurements", "At most one measurement for each of widthMM, heightMM and thicknessMM is supported.");
                foreach (var measurement in component.Measurements)
                {
                    var actual = measurement.Field switch { "widthMM" => component.WidthMM, "heightMM" => component.HeightMM, "thicknessMM" => component.ThicknessMM, _ => double.NaN };
                    Need(Positive(measurement.DesignValueMM) && Positive(measurement.MeasuredValueMM) && Positive(measurement.UsedValueMM) && measurement.UsedValueMM == actual, "cladding-measurements", "Retain finite positive design/measured/used values; explicit used value must equal geometry.");
                    Text(measurement.AdoptionBasis, "AdoptionBasis");
                }
            }
        }
        if (r.SourceMode == "selected_managed") Need(usedSources.SetEquals(sourceIds), "cladding-sources", "Every selected source must be represented; none may be silently omitted.");
        Need(r.Snapshot.Entities.Length + r.Components.Length <= PlanValidator.MaxObjects, "object-limit", "Adoption would exceed the managed-object limit.");
        if (r.Evidence is { } evidence)
        {
            Need(evidence.SourceDrawingSha256 is null || evidence.SourceDrawingSha256.Length == 64 && evidence.SourceDrawingSha256.All(Uri.IsHexDigit), "cladding-evidence", "Source drawing hash must be a SHA-256 digest when supplied.");
            Text(evidence.DesignBasis, "DesignBasis");
            Need(evidence.Assumptions is { Length: <= 64 } && evidence.Assumptions.All(x => !string.IsNullOrWhiteSpace(x) && x.Length <= 512 && !x.Any(char.IsControl)), "cladding-evidence", "Assumptions must be explicit bounded text.");
        }
        if (r.Stock is { } stock)
        {
            Need(Positive(stock.WidthMM) && Positive(stock.HeightMM) && double.IsFinite(stock.GapMM) && stock.GapMM is >= 0 and <= 100000 && double.IsFinite(stock.EdgeMarginMM) && stock.EdgeMarginMM >= 0 && stock.EdgeMarginMM * 2 < Math.Min(stock.WidthMM, stock.HeightMM), "cladding-stock", "Stock dimensions, gap and usable edge margins must be explicit, finite and bounded.");
        }
    }
    public static BoxSpec Box(PlateComponent c) => c.Plane switch { "XZ" => new(c.OriginMM, c.WidthMM, c.ThicknessMM, c.HeightMM), "YZ" => new(c.OriginMM, c.ThicknessMM, c.WidthMM, c.HeightMM), _ => new(c.OriginMM, c.WidthMM, c.HeightMM, c.ThicknessMM) };
    private static BoxSpec DesignBox(PlateComponent c)
    {
        double Original(string field, double fallback) => c.Measurements?.FirstOrDefault(m => m is not null && m.Field == field)?.DesignValueMM ?? fallback;
        return Box(c with { WidthMM = Original("widthMM", c.WidthMM), HeightMM = Original("heightMM", c.HeightMM), ThicknessMM = Original("thicknessMM", c.ThicknessMM) });
    }
    private static bool Positive(double value) => double.IsFinite(value) && value is > 0 and <= 100000;
    private static void ValidateBox(BoxSpec box, double tolerance)
    {
        Need(box is not null && box.Origin is not null, "cladding-geometry", "An explicit origin and dimensions are required.");
        Need(new[] { box!.Origin.X, box.Origin.Y, box.Origin.Z }.All(x => double.IsFinite(x) && Math.Abs(x) <= 10000000), "cladding-origin", "World origin coordinates must be finite and no greater than 10000000 mm in magnitude.");
        Need(Positive(box.Width) && Positive(box.Depth) && Positive(box.Height) && Math.Min(box.Width, Math.Min(box.Depth, box.Height)) > tolerance, "cladding-geometry", "Plate dimensions must exceed model tolerance, be <=100000 mm, and thickness must not exceed width or height.");
    }
    private static void Text(string value, string field) => Need(!string.IsNullOrWhiteSpace(value) && value.Length <= 128 && !value.Any(char.IsControl), "cladding-text", $"Explicit {field} text (1–128 characters without control characters) is required.");
    private static void Need([System.Diagnostics.CodeAnalysis.DoesNotReturnIf(false)] bool valid, string code, string message) { if (!valid) throw new HarnessException(code, message); }
    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", RegexOptions.CultureInvariant)] private static partial Regex EntityIdPattern();
}
