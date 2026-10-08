# Rhino AI Agent Harness — Stage 1 implementation candidate

**Status: REVIEW. Not a production release. Live Windows/Rhino acceptance has not run.**

This module implements the first slice of the existing [product specification](SPEC.md), revised to v0.2 from upstream commit `9561a0b929f9191e66230196d1be1d7453115aff`. It does not replace or merge the independent `cladding-delivery` and `cad-fabrication-engineering-v3` packages.

## What is implemented

- Actual C# RhinoCommon/Eto plugin project, with floating and dockable entry points, document-bound adapter and detached display preview.
- Separate ASP.NET Core loopback Host, versioned structured requests, an ephemeral per-session bearer nonce and persistent task/operation records.
- Narrow deterministic tools: managed box creation, managed-object translation, and managed-scope checkpoint restore.
- UI-thread reads/mutations, expected document/session/revision/snapshot checks, exact-preview binding, serialized apply, owned Undo records, post-effect QA and before-image compensation.
- Durable executor before-images plus Host task state; operation-ID/payload-hash replay protection; ambiguous apply is quarantined instead of automatically repeated.
- Per-object engineering IDs, copy-collision detection, manual edit and Undo/Redo invalidation, saved document identity and explicit save/reopen qualification steps.
- Automated fault-injection and HTTP integration tests, plus a fail-closed technical release gate.

This is a structured-tool foundation. Natural-language LLM planning, cladding integration, general modeling tool coverage, drawing/BOM/nesting output, general Revert/merge, arbitrary code execution and production approval are **not implemented** in this stage.

## Project layout

- `src/RhinoAi.Contracts`: versioned DTOs and detached adapter contracts
- `src/RhinoAi.Core`: validation, exact-preview approval, durable executor journal and execution coordination
- `src/RhinoAi.Host`: real loopback HTTP service and durable Host task journal
- `src/RhinoAi.Plugin`: real Rhino/Eto assembly and UI-thread adapter
- `tests/RhinoAi.Core.Tests`: deterministic fault-injection tests with a fake adapter
- `tests/RhinoAi.Host.IntegrationTests`: real process/HTTP tests without Rhino
- `evidence/`: actual build/test results and explicit acceptance status
- `scripts/release_gate.py`: fail-closed acceptance gate; it never grants engineering production approval

## Runtime and dependency pinning

Build with .NET SDK 8.0.425 (the patch can roll forward within the SDK feature band, as defined in `global.json`). The plugin targets `net8.0-windows`; Host/Core target `net8.0`.

The initial qualification target is Windows Rhino **8.20 running .NET 8**. The official RhinoCommon NuGet feed exposes the 8.20 reference as `8.20.25147.11001-rc`, which is pinned exactly with its transitive Eto reference in `packages.lock.json`. This is an SDK-reference compilation target, not evidence that a Rhino release candidate was executed. Newer Rhino/service-release/runtime combinations need explicit live qualification. .NET Framework, macOS Rhino and Linux Rhino execution are not qualified.

The framework-dependent ASP.NET Host additionally requires Microsoft.AspNetCore.App 8.0 on Windows; Rhino’s embedded runtime alone does not establish that prerequisite. A supplied win-x64 apphost is a cross-built candidate, not a live Windows qualification.

RhinoCommon/Eto are compile references supplied by Rhino at runtime. This project does not bundle a fake SDK or use Rhino.Compute. The cross-platform Host can run on Linux, but this does not provide a Linux Rhino executor.

## Reproduce verification

From this module root:

```sh
dotnet restore RhinoAi.sln --locked-mode -m:1
dotnet build RhinoAi.sln --no-restore -c Release -m:1
dotnet tests/RhinoAi.Core.Tests/bin/Release/net8.0/RhinoAi.Core.Tests.dll
dotnet tests/RhinoAi.Host.IntegrationTests/bin/Release/net8.0/RhinoAi.Host.IntegrationTests.dll
python3 scripts/test_release_gate.py
python3 scripts/release_gate.py evidence/acceptance.json
```

The final command deliberately exits **2 (BLOCKED)** while required live Rhino checks remain `NOT_RUN`/`BLOCKED`. A green build/headless test run must not be relabeled as a complete Stage 1 pass.

`DOTNET=/path/to/dotnet bash scripts/publish-windows.sh` cross-builds the framework-dependent Windows Host and collects the separately built plugin; its separate `packages.win-x64.lock.json` files preserve the normal build locks. Windows execution is still unqualified.

`DOTNET=/path/to/dotnet bash scripts/verify.sh` runs the same sequence and records logs. In a read-only-home container, set `DOTNET_CLI_HOME`, `NUGET_PACKAGES` and `NUGET_HTTP_CACHE_PATH` to writable temporary directories. No change to the user's machine, network/security settings or account credentials is needed for these cloud checks.

## How to qualify in Rhino

See [the live plugin runbook](src/RhinoAi.Plugin/LIVE-ACCEPTANCE.md) and [Host runbook](docs/host-runbook.md) for exact launch and UI steps. Install/load only when the user authorizes it on their Windows Rhino workstation. The provided source is not an installer and has not been installed on the user's computer.

Acceptance must cover Preview/Reject, accepted Commit, native Undo/Redo, manual copy and replace, document switch/close, save/reopen, checkpoint restore, lost acknowledgement, cancellation and failure recovery. Record the exact Rhino build, runtime, source digest and evidence. Chinese model/drawing-label rendering is not qualified here; the foundation uses ASCII labels and preserves a separate engineering identity.

## Recovery boundaries

- Native Undo is neither an ACID transaction nor a durable filesystem rollback.
- Checkpoints in this stage contain the explicitly supported **managed-object scope**. Unmanaged objects are preserved, and later edits to managed objects are replaced only after an explicit restore preview/acceptance.
- A failed or ambiguous apply quarantines further mutation. Automatic recovery unlock and general history merge are not implemented. Preserve the actual model, executor/Host journals and checkpoint, then perform a reviewed manual reconciliation.
- Local journal flush + atomic file replacement addresses process-crash recovery. Sudden power loss, device failure, directory-entry durability and cross-process model/journal consistency are not ACID guarantees.
- Original DWG/3DM files are never silently overwritten. Export/order publication is outside this stage.

## Delivery stages

1. Dependable Plugin/Host vertical loop and live Rhino acceptance.
2. First supported cladding scenario, LLM/Skill integration and same-snapshot review outputs.
3. Isolated expert Code Mode, Vision, branches/comparison, milestones and Grasshopper.
4. Team/remote platform and centrally governed sharing.

See [SPEC.md](SPEC.md) sections 34–46 for scope and mandatory contracts. Local source/build work does not imply repository push, PR, deployment or production approval.
