# Controlled external CAD runtime integration (v3.4 local review build)

## What is actually connected

`cadfab_v3.backends.provider` invokes an installed runtime through a selected Python executable, with argument arrays, isolated import paths and a timeout. It does not bundle cadgen, build123d, CadQuery, OCP, viewer assets or runtime source.

- `cadquery` (default): existing compatibility B-Rep builder and STEP exporter.
- `build123d`: generated parameterless model source, `Box`/`Compound` and `build123d.export_step` in the selected external interpreter. Verified adapter versions: 0.10.0 and 0.11.1.
- `cadgen`: generated parameterless `@step(out=...)` entrypoint, `from cadgen import build123d as bd`, executed through cadgen's real model pipeline. Version 0.7.15 is the currently inspected/pinned public API. Changing that pin requires revalidation, not an automatic upgrade.
- `auto`: explicitly permits availability selection in cadgen → build123d → CadQuery order. A selected provider's build failure never changes provider. Explicit provider selection never falls back.

The default is deliberately compatibility-preserving. Installing a package alone does not change an existing project's provider. Record backend and external Python in `cad_runtime` or use CLI flags. The runner imports the selected provider's saved STEP back through CadQuery/OCP and passes that shape to the drawing layer. Drawings therefore derive from the saved selected-provider artifact, not a separately regenerated model.

## Verified scope and fail-closed limits

All three adapters implement the same limited canonical IR: positive rectangular nominal sheet solids in XY/XZ, in mm, with one explicit occurrence per part. They do not turn natural language or raw DWG into verified engineering decisions. Production status, fabrication solids, undeclared part features, unsupported geometry fields, and requested sections/curves/unfolding fail before delivery. Adding another exporter does not validate nodes, folds, structural adequacy, connections, drainage, or purchase quantities.

The engineering-document implementation remains this skill's OCCT HLR + ReportLab/PyMuPDF + ezdxf path. Upstream `cadgen.eng_drawing` emits PDF only and currently has no sections, details or auxiliary views. This adapter does not claim to call that PDF API or to gain a complete DXF/section engineering system by installing cadgen. The nominal-face DXF remains reference-only.

Every selected-provider STEP is re-opened and checked for valid solids, exact count, each solid's placement and dimensions, and volume against the canonical IR. This is geometry verification for the declared nominal adapter, not production qualification. Manifest provenance records requested/selected provider, availability failures, interpreter, package versions/module origin, adapter contract, generated source hash and actual STEP hash. `production_qualified` is always false.

## Installation and repeatable validation

See [External runtime setup](runtime-setup.md). Keep environments outside the skill package. The compatibility/drawing interpreter and the cadgen interpreter are separate: current cadgen requires build123d 0.11.1 and OCP 7.9, while older CadQuery environments may use OCP 7.8. The artifact boundary is STEP, not mixing two incompatible OCP installations in one process.

Do not install a runtime automatically at project-run time. Use trusted registry/vendor installation under the user's authorization; check licensing for the environment. Setup does not edit the upstream plugin, its skills or its runtime internals.

`SOURCE/<project>.py` in an external-provider delivery is the exact parameterless entrypoint; its input is sibling `geometry_ir.json`. Treat both as provenance, edit project configuration and regenerate into a new directory. The runner refuses an existing output directory and existing output STEP, keeps an exact configuration snapshot and hash, and checks that the original configuration was not changed during execution.

## Upstream sources inspected

- [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad), MIT; PyPI distribution `cadgen==0.7.15`.
- [CAD model contract](https://github.com/earthtojake/text-to-cad/blob/main/skills/cad/references/step-generation.md): parameterless decorated models, source execution and external runtime store.
- [Engineering drawing skill](https://github.com/earthtojake/text-to-cad/blob/main/skills/engineering-drawing/SKILL.md): PDF-only output and projection limitations.
- [Runtime metadata](https://github.com/earthtojake/text-to-cad/blob/main/packages/cadgen/pyproject.toml): Python >=3.11, cadgen 0.7.15, build123d >=0.11.1,<0.12, cadquery-ocp-novtk >=7.9,<8.

Local test provenance must distinguish import/kernel readiness from decorated export acceptance. In the managed review environment, cadgen's kernel probe succeeds but its required local IPC broker socket is denied (`PermissionError: Operation not permitted`), including a scoped escalated attempt. The integration test records this as BLOCKED/SKIPPED, not a successful cadgen export. CadQuery and both tested build123d versions execute real STEP exports and readback checks here. A deployment must run the cadgen export test successfully before treating that provider as locally accepted.
