namespace RhinoAi.Contracts;

/// <summary>Explicit engineering inputs. All lengths are millimetres, never inferred from a prompt.</summary>
public sealed record PlateMeasurement(string Field, double DesignValueMM, double MeasuredValueMM, double UsedValueMM, string AdoptionBasis);
public sealed record PlateStock(double WidthMM, double HeightMM, double GapMM, double EdgeMarginMM, bool ProcessConfirmed);
public sealed record SelectedPlateSource(string EntityId, string Fingerprint, BoxSpec BoxMM);
public sealed record PlateComponent(string EntityId, string DisplayLabel, Point3 OriginMM, double WidthMM, double HeightMM,
    double ThicknessMM, string Material, string Grade, double DensityKgM3, int Quantity, string[] SourceEntityIds,
    PlateMeasurement[]? Measurements = null, string[]? Features = null, string GeometryType = "planar_plate", string Plane = "XY");
public sealed record CladdingSourceEvidence(string? SourceDrawingSha256, string DesignBasis, string[] Assumptions);
public sealed record CladdingReviewRequest(int ProtocolVersion, Guid JobId, ExpectedContext Expected, DocumentSnapshot Snapshot,
    string SourceMode, string[] SelectedEntityIds, SelectedPlateSource[] Sources, PlateComponent[] Components,
    string[] Targets, PlateStock? Stock = null, CladdingSourceEvidence? Evidence = null);
public sealed record CladdingPreviewPlate(string EntityId, BoxSpec Box, string Material);
public sealed record CladdingArtifact(string Path, string Sha256, long Bytes, string Kind, string? EntityId = null);
public sealed record CladdingReviewManifest(int ProtocolVersion, Guid JobId, string RequestHash, string InputSnapshotHash,
    string JobHash, string RuleVersion, string SkillVersion, string SkillSourceHash, string Status, bool ManufacturingRelease,
    string ReleaseDecision, string NestingStatus, CladdingPreviewPlate[] PreviewPlates, CladdingArtifact[] Artifacts, string[] Warnings);
/// <summary>Immutable completed review. The manifest digest is calculated from the stored bytes by the Host.</summary>
public sealed record CladdingReviewResult(CladdingReviewManifest Manifest, string ManifestHash, CladdingReviewRequest Request, string OutputDirectory);
public sealed record CladdingAdapterEnvelope(string RequestHash, string InputSnapshotHash, string JobHash, string RuleVersion,
    string SkillVersion, string SkillSourceHash, CladdingReviewRequest Request);
