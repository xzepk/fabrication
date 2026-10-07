# Controlled modeling and provider acceptance

This skill is independent: it never imports, invokes, or requires the CAD processing skill. Reuse is limited to externally installed open-source libraries.

## Provider capability matrix

| Route | Executable behavior | Scope |
|---|---|---|
| `occt` (default) | CadQuery/OCP templates; STEP + STL, STEP readback | Plain rectangular plate and sharp-corner open rectangular tube |
| `build123d` (optional) | build123d templates; STEP + STL, STEP readback through CadQuery/OCP | Same two types; no silent fallback |
| `rhino` (optional) | Controlled HTTP adapter with shared-filesystem STEP output; local readback | Same locally validated two types until a project adapter is implemented and validated |
| `proposal-import --engine text-to-cad/cadgen` | Data-only canonical JSON staging with hash/identity/capability report | Candidate review only; no generated code, CAD skill calls, runtime install, or active-model mutation |

Only documented component root keys are accepted; annotations belong in inert `metadata`, which never controls geometry. Top-level fabrication/unknown feature containers are rejected. Both built-in modeling providers reject holes, folds/bends, slots, custom profiles, ribs, flanges, fillets, chamfers, notches and every unknown geometry field BEFORE export. Empty feature arrays/objects are allowed as no features; nonempty features are blockers. Numeric dimensions must be finite and positive; tube wall must leave a void. Only mm is implemented. Units/transforms must be resolved into the canonical model before import. The rectangular tube is a sharp-corner idealization, not a claim about real rolled-section corner radii.

DXF unfold uses one closed rectangular CUT contour at true millimetre scale and one ASCII INFO ID. INFO is identification only, never a cut operation. DXF header units, contour closure and coordinates are read back. The original ID and display label are preserved exactly in UTF-8 JSON/BOM maps. Do not infer Chinese font availability from valid Unicode or send INFO to a cutter.

## Why build123d is integrated, but cadgen is not a production provider

The upstream [text-to-cad repository](https://github.com/earthtojake/text-to-cad) is a model-script workflow. Its [CAD skill](https://github.com/earthtojake/text-to-cad/blob/main/skills/cad/SKILL.md) and [modeling reference](https://github.com/earthtojake/text-to-cad/blob/main/skills/cad/references/build123d-modeling.md) describe Python model functions using build123d. That capability is useful for exploring models; it does not supply this project's scope confirmation, site survey, fabrication parameters, or per-part acceptance.

For this 3.1.0 local review build, a small deterministic build123d template provider is integrated and tested. cadgen is deliberately **not installed, executed, or declared tested**. An external cadgen/text-to-cad session can supply reviewed JSON dimensions and evidence, but arbitrary model scripts are not executed inside this skill. A subprocess alone is not a security sandbox, and a generated STEP alone is not evidence of approved manufacturing intent.

To stage a candidate without changing the active model:

```bash
python <skill>/scripts/run.py --project <project> proposal-import <candidate.json> --engine cadgen
```

The output lives in `work/proposals/<input-sha256>/`. Review the original drawing/dimension/material evidence and the report. Only then explicitly use `components-import` on the reviewed candidate and obtain a current scope confirmation before `run`. Unsupported features remain blocked even after staging or importing; a human confirmation cannot create missing geometry capability. Staging is outside the active snapshot and never invalidates/approves the active model by itself.

## What geometric acceptance establishes

Every model export is re-imported from the real STEP bytes. Acceptance checks BRep validity, exactly one solid with closed boundary shells, measured positive volume and surface area, expected extents and placement. Rectangular tubes also test that the center is void and a wall point is inside. Numerical readback limits are 1e-5 mm absolute for length and 1e-7 relative for mass properties; these are serialization/model-consistency checks, **not machining or installation tolerances**. Analytic expected values are stored separately; BOM uses re-imported measured volume.

Each run stores effective components, identity mappings and artifact SHA256 values. `verify` checks files/hashes and re-imports every successful STEP again. `package` refuses corrupt/incomplete artifacts. A geometrically consistent REVIEW package still requires engineering/manufacturing review. STL is a tessellated preview, not a dimensional master or CNC toolpath.

## Rhino adapter contract tightening

POST `/v1/build-component` receives `component`, `identity`, `units: mm`, and the exact `output_step` path. The adapter must share that output filesystem, write that STEP, and return `step` at exactly that path. Remote-only URLs and server-reported metrics are insufficient. Arbitrary URLs are not downloaded. Plain-plate DXF is generated and checked locally; complex `/unroll-component` is not invoked. Rhino requires an explicit project configuration; unavailable service or rejected output stops that component. No Rhino service or license was exercised by the Linux built-in provider tests.

`production_blocked` reports detected technical issues only. Every run also explicitly records `manufacturing_release: false` and `production_qualified: false`, even when no technical issues are detected. A changed current project snapshot makes a historical run stale; it cannot be repackaged as current without a confirmed rerun.

Run result artifact paths are relative to their run, so copying the complete project preserves verification. A REVIEW zip contains that run's artifacts and captured input snapshot, not the mutable project's current config/confirmations; current-project verification requires the complete project state. Hashes and captured expected dimensions remain available for independent artifact review.
