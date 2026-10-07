---
name: cad-fabrication-engineering-v3
description: >-
  Engineering-grade CAD deepening and fabrication workflow for architectural, curtain-wall, canopy and metal-cladding projects. Parses traceable DWG/DXF evidence into Geometry IR, generates deterministic B-Rep/STEP models, projects professional engineering drawings from the B-Rep, creates controlled DXF/BOM outputs, applies survey changes, and runs cross-artifact QA. Use when engineering drawings must be clearer and more reliable than LLM-authored CAD sketches. Includes explicit external text-to-cad cadgen/build123d provider integration and a CadQuery compatibility route. The current runnable model adapter is limited to nominal rectangular XY/XZ panels; complex geometry requires a separately verified adapter. Never substitutes a nominal face layout for a true fabrication flat pattern.
compatibility: >-
  Windows 10/11 or Linux; Python 3.11+. CAD runtime choices: external cadgen 0.7.15 or build123d 0.10.0/0.11.1; default compatibility route: externally installed CadQuery/OCP + ezdxf + ReportLab/PyMuPDF. Production DWG parsing uses external runtime adapters only: ACadSharp/.NET 8+ is the primary environment dependency; ODA Drawings SDK/helper is an optional external fallback. Neither runtime nor helper binaries/source are bundled in this skill. Rhino.Compute is an optional project-specific extension, not implemented by the reference runner.
metadata:
  version: "3.4.0"
  ir_version: "1.1"
  domain: "architectural-cad-fabrication"
  architecture: "evidence-geometry-ir-parametric-brep-projected-drawing"
---

# CAD Fabrication Engineering v3.4

## Mission

Use the Agent for intent, planning, semantic resolution, exception handling and engineering explanation. Use parsers, Geometry IR, geometric kernels, projection engines and deterministic QA as the numerical source of truth.

The target is **engineering deepening and fabrication preparation**, not “AI draws something that looks like CAD”.

## Mandatory workflow

Do not bypass the engineering gates:

1. **图纸解析 / Parse** - fingerprint the source; preserve handles, layers, blocks/XRefs, transforms, dimensions and parser warnings.
2. **语义归一 / Normalize** - convert parser evidence into canonical Geometry IR without silently inventing unresolved semantics.
3. **方案确认 / HUMAN GATE A** - confirm scope, material, thickness, finish, joints, panelization, nodes, folds/returns, holes and fabrication allowances.
4. **参数化深化 / Parametric Deepening** - build deterministic B-Rep geometry from Geometry IR.
5. **工程图 / Documentation** - project views from the same B-Rep used for STEP; derive dimensions/schedules from Geometry IR/model facts.
6. **现场复尺 / HUMAN GATE B** - apply stable measurement IDs, compute deltas and invalidate affected downstream artifacts.
7. **生产文件 / Produce** - regenerate STEP/PDF/DXF/BOM from the confirmed IR and survey snapshot.
8. **QA + Golden Regression / Deliver** - re-open artifacts, audit them, render PDF sheets, inspect visually, and package only after status/gates are explicit.

## Core contract: Geometry IR 1.1

Downstream code MUST NOT consume parser SDK objects or LLM-authored final DXF entities. It consumes Geometry IR.

Geometry IR 1.1 distinguishes:

- source evidence and source-dimension semantics;
- release gates and confidence/blocking assumptions;
- project datums/set-out geometry;
- nominal cladding envelope versus fabrication geometry;
- stable part/panel identities and locations;
- material and fabrication attributes;
- quantities that are actually known versus quantities that are unavailable.

### Never collapse different geometric meanings into one field

For example, a top projection of `1190 + 1170 + 1170 = 3530 mm` plus a vertical fascia drop of `600 mm` may form a **4130 mm reference developed/profile chain**. It is not therefore a 4130 mm plan depth.

Use distinct fields such as:

- `top_projection_depth`;
- `front_fascia_drop`;
- `profile_path_length_ref`.

When the source semantic is not confirmed, keep it as a source/reference dimension with an assumption and blocking status.

## Geometry maturity levels

Every output declares one geometry level:

1. `NOMINAL_SKIN` - panel face/envelope; useful for panelization and design review.
2. `FABRICATION_SOLID` - confirmed returns, bends, holes, reliefs and fabrication features are modeled.
3. `ASSEMBLY_MODEL` - fabrication parts plus required interfaces/subframe/components.

A `NOMINAL_SKIN` rectangle or plate MUST NOT be called a flat pattern.

A production flat pattern can be released only when:

- the fabrication solid exists;
- bend/return rules are confirmed;
- node-specific reliefs/holes are known;
- the unfolding operation succeeds and passes QA.

## CAD backend policy

### Controlled providers, explicit selection

The reference runner supports `--backend cadquery|build123d|cadgen|auto`; default `cadquery` preserves existing projects. `cadgen` invokes the actual external 0.7.15 parameterless `@step` API. `build123d` invokes the selected external interpreter's geometry/export API. `--runtime-python` selects that environment. Only explicit `auto` permits availability fallback; a selected provider's build failure is always fatal.

Keep all runtimes outside this skill. Read [integration contract](references/text-to-cad-integration.md) for scope, provenance and upstream API limits, and [runtime setup](references/runtime-setup.md) for separate environments and acceptance commands.

For all providers, drawings use the saved STEP readback, OCCT HLR, ReportLab/PyMuPDF and ezdxf. The upstream cadgen engineering-drawing API is PDF-only and has no sections/details; the skill does not claim to invoke that API or obtain complete DXF engineering from it. Re-open STEP/PDF/DXF, review the rendered previews, and regenerate from source rather than patching final geometry.

### Reference adapter boundary

The runnable adapter currently verifies nominal rectangular panels in XY/XZ only. Unsupported geometry/features/capability requirements and production release are refused. This is not a general-purpose cladding, bending, NURBS, node-detail or true-unfolding solver. A Rhino.Compute or other advanced route must be implemented and independently verified for its project before claiming support; it is not selected by this runner.

## Production DWG parser policy

DWG runtimes are **environment dependencies, not skill contents**. This package MUST NOT bundle ACadSharp, .NET, ODA Drawings SDK, ODA helper binaries, or runtime-specific source projects.

### Runtime priority

1. `acadsharp` — **default and primary** production parser for supported DWG entities. The environment provides a compliant ACadSharp adapter command.
2. `oda` — **optional external fallback** for drawings where ACadSharp coverage is insufficient, especially proxy/custom-object fidelity or other unsupported constructs. The environment provides a compliant ODA adapter command.
3. explicit DXF + ezdxf — diagnostic/compatibility route only unless the project separately approves it.
4. LibreDWG — diagnostic only unless separately validated by the organization.

The skill never silently changes parser. Default policy is `acadsharp`. ODA is used only when the project/user explicitly selects `oda`, or explicitly selects `auto` and the ACadSharp attempt fails. Parser outputs are never silently merged.

### External adapter commands

The environment exposes commands through:

- `CADFAB_ACADSHARP_CMD` (default command name: `cadfab-acadsharp-dump`)
- `CADFAB_ODA_CMD` (default command name: `cadfab-oda-dump`)

Both commands must implement the same adapter contract in `references/dwg-adapter-contract.md`. The skill owns the contract, normalization and QA; the environment owns installation, licensing and runtime lifecycle.

Preflight without parsing:

```bash
python scripts/dwg_preflight.py drawing.dwg --check-only
```

Run the primary parser:

```bash
python scripts/dwg_preflight.py drawing.dwg --parser acadsharp --out-dir work/parser_raw
```

Explicit ODA fallback:

```bash
python scripts/dwg_preflight.py drawing.dwg --parser oda --out-dir work/parser_raw
```

Explicit controlled fallback policy:

```bash
python scripts/dwg_preflight.py drawing.dwg --parser auto --out-dir work/parser_raw
```

`auto` means ACadSharp first, then ODA only if the ACadSharp adapter cannot successfully complete. It does not mean "pick whichever happens to be installed first", and it does not merge entity streams. The manifest must record every attempted adapter and the selected parser.

Unsupported proxies, unresolved XRefs, missing fonts, unknown units, dimension failures and custom objects are explicit issues. A parser process returning exit code 0 is not sufficient for production readiness; entity coverage and parser notifications must still pass QA.

## Professional drawing contract

A controlled engineering PDF is a document derived from model geometry, not a screenshot and not a hand-redrawn approximation.

### Required drawing behavior

- project orthographic/isometric linework from the B-Rep;
- use real view scales and `AS SHOWN` when scales differ by view;
- use visible/hidden/joint/reference line hierarchy;
- show overall dimensions and concise set-out chains;
- use `N EQ @ pitch` for repeated equal bays instead of 14 identical dimensions;
- show panel IDs through a complete plan/elevation/schedule/mark matrix;
- separate nominal face dimensions from fabrication flat patterns;
- label profiles honestly: do not call an envelope profile a structural section;
- include drawing number, revision, sheet number, units, scale and release status;
- display unresolved release blockers on the drawing or schedule.

### Minimum PDF QA

The generated PDF must pass automated checks for:

- expected page count;
- release status on every sheet;
- no text outside page bounds;
- 100% controlled panel-ID coverage;
- minimum text size warning threshold;
- B-Rep-projected view source.

Then render every sheet to PNG and visually inspect it. Automated checks do not prove that a leader, note or dimension is aesthetically ideal.

For stable Chinese text in controlled PDFs, the runner first discovers an embeddable system CJK font. Set `CADFAB_CJK_FONT` to an approved font path as an exclusive override: a missing/inadequate override is not silently replaced by another font. The skill does not bundle fonts. Optional config `display_labels` maps exact original text to reviewed English/pinyin ASCII; the runner preserves it in IR. Unknown untranslated safety notes fail QA. Original IDs remain in IR/BOM/manifests alongside portable display/file labels and mapping sidecars.

Read `references/cad-quality-standard.md` before changing drawing layout code.

## Engineering DXF contract

Engineering DXF is 1:1 model-space projected linework for CAD interoperability. Use semantic layers and lineweights, including:

- `A-VIEW-VISIBLE`
- `A-VIEW-HIDDEN`
- `A-PANEL-JOINT`
- `A-DIM`
- `A-TEXT`
- `A-CENTER`
- `A-REF`
- `A-WARNING`

A reference nominal-face layout uses a different artifact role and carries a visible warning. Do not name it a flat pattern or nesting file.

## Material and quantity contract

Keep these quantities separate:

- net visible/nominal face area;
- estimated net sheet mass from nominal face area;
- true unfolded blank area;
- purchase area after nesting/waste policy.

If no true unfold exists, blank area and purchase area stay `null` / `NOT AVAILABLE`.

## Complex project decomposition

Do not create one monolithic whole-building model.

Use stable hierarchy:

`Project -> Building -> Elevation/Floor/Zone -> System -> Assembly -> Part/Panel`

Reuse generators for repeated bays/nodes. Regenerate and QA only impacted partitions after survey or rule changes, then run project-level consistency checks.

## Status / release rules

Every output states one of:

- `REFERENCE_VALIDATION`
- `PRELIMINARY`
- `SURVEY_PENDING`
- `PRODUCTION_CANDIDATE`

`PRODUCTION_CANDIDATE` is invalid if any required gate is false, a blocking assumption remains, STEP/DXF/PDF QA fails, or a required true flat pattern does not exist.

Even `PRODUCTION_CANDIDATE` still requires the organization's normal release authority.

## Commands

### Reference end-to-end run

```bash
python scripts/run_project.py config/canopy-reference-validation.yaml outputs/new-review-run --backend cadquery
```

### Package validation and tests

```bash
python scripts/validate_skill.py .
PYTHONPATH=src python -m unittest discover -s tests -v
```

### Golden regression

```bash
python scripts/golden_regression.py
python scripts/golden_regression.py --output outputs/canopy_reference_validation
```

Golden samples are immutable regression references only. Never hard-code their layer names, dimensions or conventions into general production rules.

## Reference output contract

The output directory must be new; previous outputs and inputs are never deleted. A run may produce:

- `INPUTS/config.yaml` - exact original configuration snapshot;
- `SOURCE/<project>.py` - generated parameterless external-provider model, when selected;

- `geometry_ir.json` - canonical contract;
- `STEP/<project>.step` - B-Rep at declared geometry maturity;
- `DXF/<project>_engineering.dxf` - 1:1 engineering projection;
- `DXF/<project>_reference_blank_layout.dxf` - reference nominal faces only when flat pattern is unavailable;
- `PDF/<project>_engineering.pdf` - controlled engineering document;
- `BOM/<project>_bom.csv` - per-panel traceability;
- `BOM/<project>_type_schedule.csv` - grouped type schedule;
- `QA/<project>_qa.json` - cross-artifact QA;
- `PREVIEW/engineering-sheet-*.png` - rendered PDF review images;
- `manifest.json` - hashes, roles, versions, assumptions and release state.

When a true fabrication solid/unfolding workflow is available, replace the reference nominal-face artifact with an explicitly named true flat-pattern artifact and record its release state.

## Current reference validation boundary

The supplied canopy sample demonstrates the V3.4 drawing/model/QA pipeline, but its source semantics are still based on recovered dimensions because the current execution environment has not provided an external ACadSharp or ODA adapter runtime.

Therefore it intentionally remains `REFERENCE_VALIDATION` with blocking assumptions. The skill is designed to fail closed rather than upgrading that sample to production status by inference.
