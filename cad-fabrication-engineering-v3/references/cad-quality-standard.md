# CAD / drawing quality standard - v3.2

## 1. View truth

- Documentation views must be derived from the same B-Rep used for STEP. The compatibility backend uses OCCT Hidden Line Removal (HLR); the preferred cadgen backend should use its geometry-projected engineering drawing API.
- Never redraw a final orthographic view by asking the LLM to place arbitrary lines.
- A profile is not called a structural **section** unless a cut plane and the relevant structural/node geometry actually exist.
- Isometric views are supporting orientation views; dimensions belong on orthographic/detail views unless there is a specific reason.

## 2. Scale and layout

- Use ISO/A-series sheets and a real per-view scale. Use `AS SHOWN` when a sheet contains multiple scales.
- Preferred scale set: 1:1, 1:2, 1:5, 1:10, 1:20, 1:25, 1:50, 1:75, 1:100, 1:150, 1:200.
- Do not vertically exaggerate one axis in a view that is labeled as a true engineering scale.
- Use a concise set-out chain for repeated equal bays (`N EQ @ pitch`) rather than repeating the same dimension N times.
- Avoid unused page area when it can be replaced by a useful orientation view, mark matrix, release-state block or detail.

## 3. Line hierarchy

Recommended plotted weights:

- visible silhouette / principal outline: 0.35-0.50 mm;
- structure / important internal outline: 0.25-0.35 mm;
- panel joints / hidden lines / text: 0.18-0.25 mm;
- dimensions / centers / reference envelope: 0.13-0.18 mm.

Hidden lines use a hidden linetype; reference envelopes/datum extents use a light dashed line. Panel joints must read distinctly from the outer silhouette.

## 4. Annotation and numbering

- All controlled panel IDs must appear on at least one readable document sheet or schedule. Silent truncation is a QA failure.
- Dimensions must come from model/IR values; any overridden/reference-only value must be visibly marked `REF` or be described in the release-state block.
- Minimum text size target on A3: 4 pt absolute minimum, 5-7 pt preferred for schedules/notes.
- Long notes must wrap within a controlled box; they must not run through adjacent views or title blocks.
- Prefer an embeddable workstation CJK font for controlled PDFs. The skill may discover a system font or use `CADFAB_CJK_FONT`; do not bundle font files in the skill. A non-embedded CID fallback is acceptable only as a warning in non-production review.

## 5. Fabrication claims

Three geometry maturity levels are distinguished:

1. `NOMINAL_SKIN` - cladding face/envelope only; suitable for panelization and design review.
2. `FABRICATION_SOLID` - confirmed folds/returns/holes/reliefs represented in 3D.
3. `ASSEMBLY_MODEL` - fabrication parts plus interfaces/subframe/components as required by the project.

A nominal panel-face rectangle is **not** a flat pattern. A true flat pattern may be released only from a confirmed fabrication solid and bend rule set.

Material reporting must separate:

- net visible/nominal face area;
- true blank area after unfolding;
- purchase area after nesting/waste policy.

Do not turn one into another by applying an arbitrary percentage without a project rule.

## 6. Automated QA minimum

Before handoff, automatically check:

- STEP re-read, validity and expected solid count;
- dimensional closure (set-out and profile chains where relevant);
- unique IDs, positive dimensions and quantity consistency;
- PDF page count, status on every sheet, text inside page bounds and full panel-mark coverage;
- DXF audit and required semantic layers;
- no production-candidate state with unresolved blocking assumptions, missing Gate A, missing survey, or no true flat pattern when one is required;
- golden-sample fingerprints and current reference metrics.

Automated QA does not replace visual review. Render every engineering PDF sheet and inspect it before delivery.
