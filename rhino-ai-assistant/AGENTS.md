# Rhino AI Stage 1/2 repository workflow

- Start with `docs/WORKBUDDY.md`. The primary handoff is repository-only; no chat attachment, shared filesystem, or external agent credentials are required.
- On authorized Windows workstations use `scripts/workbuddy-build.ps1` and `scripts/workbuddy-verify.ps1`. Read commands before running them. Installation/loading and model mutation require the user's approved test scope.
- Preserve `cladding-delivery`, `cad-fabrication-engineering-v3`, original DWGs and production 3DMs. This module does not merge the two independent skills. Stage 2 implements only the explicitly documented local planar-plate bridge.
- Record the actual checkout commit or archive provenance. `SOURCE_BASELINE.json` and top-level `evidence/` are historical. The current source-byte manifest is `evidence/repository-workflow/source-manifest.json`; other committed logs there are historical Stage 1 evidence. Fresh Stage 2 evidence belongs to a unique ignored run directory.
- Keep every new run under this module's `artifacts/workbuddy-runs/<unique-run>/`. Never overwrite historical acceptance or reuse a failed run to hide evidence. Do not commit generated binaries, journals, models, nonces, or local evidence.
- Live Windows/Rhino F-02 through F-11 require actual live evidence. Fake-adapter/HTTP/headless results never qualify them. Missing fault-injection capability is BLOCKED, not PASS. Engineering production status always remains REVIEW; manufacturing remains NOT_RELEASED. Stage 2 development may continue while live qualification is explicitly ON HOLD, but release gates stay blocked.
- Restore is managed-object scope only; never reset journals, reinitialize an error document, bypass a license/security warning, change execution policy, or kill unrelated processes to clear a failed gate.

- Local model fixtures are not evidence of real natural-language model execution. Keep actual model qualification NOT_RUN until separately exercised. Preserve structured local self-use without requiring a provider or credentials.
- Stage 2 changes require actual controlled Skill-process and artifact readback tests. Reject unsupported features, mixed snapshots, unsafe paths and partial outputs; never execute model-generated code.
