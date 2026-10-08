# Rhino AI Stage 1 repository workflow

- Start with `docs/WORKBUDDY.md`. The primary handoff is repository-only; no chat attachment, shared filesystem, or external agent credentials are required.
- On authorized Windows workstations use `scripts/workbuddy-build.ps1` and `scripts/workbuddy-verify.ps1`. Read commands before running them. Installation/loading and model mutation require the user's approved test scope.
- Preserve `cladding-delivery`, `cad-fabrication-engineering-v3`, original DWGs and production 3DMs. This module does not merge the two independent skills or implement Phase 2.
- Record the actual checkout commit or archive provenance. `SOURCE_BASELINE.json` and top-level `evidence/` are historical. Current committed headless evidence and source manifest are in `evidence/repository-workflow/`.
- Keep every new run under this module's `artifacts/workbuddy-runs/<unique-run>/`. Never overwrite historical acceptance or reuse a failed run to hide evidence. Do not commit generated binaries, journals, models, nonces, or local evidence.
- Live Windows/Rhino F-02 through F-11 require actual live evidence. Fake-adapter/HTTP/headless results never qualify them. Missing fault-injection capability is BLOCKED, not PASS. Engineering production status always remains REVIEW in Stage 1.
- Restore is managed-object scope only; never reset journals, reinitialize an error document, bypass a license/security warning, change execution policy, or kill unrelated processes to clear a failed gate.
