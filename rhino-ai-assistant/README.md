# Rhino AI Agent Harness — Stage 2 first integration candidate

**Status: Stage 2 first integration candidate, REVIEW. This is not complete single-machine cladding automation or a production release. Live Windows/Rhino acceptance has not run.**

This module extends the foundational slice with the local self-use candidate in [specification v0.3](SPEC.md). Stage 2 development continues with Windows/Rhino qualification explicitly on hold. It does not replace or merge the independent `cladding-delivery` and `cad-fabrication-engineering-v3` packages.

## WorkBuddy: start from this repository

**[中文主操作说明：从仓库构建、加载与实机验收](docs/WORKBUDDY.md)**

Use an authenticated clone or a GitHub source archive of the selected commit. No chat ZIP, Library attachment, prebuilt binary, or other assistant's filesystem is required. For a new clone, use `git clone -c core.autocrlf=false https://github.com/xzepk/fabrication.git` so checkout preserves the source bytes; this does not change global Git settings. Record the actual checkout HEAD or archive commit. `SOURCE_BASELINE.json` describes the earlier specification baseline, not the current implementation commit.

On an authorized Windows x64 test workstation, use the repository-native PowerShell workflow:

```powershell
# From rhino-ai-assistant/. Use a fresh run directory every time.
$Source = (Get-Location).Path
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$RunRoot = Join-Path $Source ('artifacts\workbuddy-runs\' + $RunId)
.\scripts\workbuddy-build.ps1 -SourcePath $Source -RunRoot $RunRoot
# After recording actual live results, verify the same run:
.\scripts\workbuddy-verify.ps1 -SourcePath $Source -RunRoot $RunRoot
```

The build script verifies the committed [repository-workflow source manifest](evidence/repository-workflow/source-manifest.json), uses locked dependencies, runs automated tests, and builds the framework-dependent win-x64 Host and `.rhp` locally. It creates candidate hashes, logs, `acceptance.local.json`, and `live-cases.json` under the new run directory. GitHub archive users supply the verified full commit with `-SourceCommit`; optional `-Dotnet` and `-Python` accept existing tool paths. The [runbook](docs/WORKBUDDY.md) covers all parameters, permissions, exact GUI steps, L-01–L-20/F-01–F-12 coverage, and safe failure handling.

A successful build exits 0 for build/headless tests and separately records the initial gate exit code in `build-result.json`. The verifier preserves previous gate logs and never overwrites historical acceptance. **Exit 2 / BLOCKED is expected until required live Rhino checks are actually completed.** Missing debugger/fault-injection capability blocks L-15/L-16/L-18 and the affected gates; ordinary GUI checks can still proceed. Build success is not installation, live acceptance, or production approval. No compiled candidate binaries are committed.

## Supported first integration and remaining everyday-workflow gaps

Selected-source intake currently requires already managed, verified axis-aligned boxes. Arbitrary existing unmanaged Rhino geometry or original DWG interpretation/adoption is not implemented. Automatic panelization is not implemented. A genuine broader everyday workflow still needs an explicit design for source recognition/adoption and panelization, plus actual Windows/Rhino and local-model qualification. Do not replace these gaps with bounding-box simplification or manufacturing assumptions.

## What is implemented

- Actual C# RhinoCommon/Eto plugin project, with floating and dockable entry points, document-bound adapter and detached display preview.
- Separate ASP.NET Core loopback Host, versioned structured requests, an ephemeral per-session bearer nonce and persistent task/operation records.
- Narrow deterministic tools: managed box creation, managed-object translation, and managed-scope checkpoint restore.
- UI-thread reads/mutations, expected document/session/revision/snapshot checks, exact-preview binding, serialized apply, owned Undo records, post-effect QA and before-image compensation.
- Durable executor before-images plus Host task state; operation-ID/payload-hash replay protection; ambiguous apply is quarantined instead of automatically repeated.
- Per-object engineering IDs, copy-collision detection, manual edit and Undo/Redo invalidation, saved document identity and explicit save/reopen qualification steps.
- Automated fault-injection and HTTP integration tests, plus a fail-closed technical release gate.

Stage 2 adds bounded local-model planning and the independent cladding planar-plate review workflow. See [local self-use](docs/STAGE2-LOCAL.md) for exact contracts, configuration, supported geometry and honest verification status. Actual local-model and Windows/Rhino execution remain NOT_RUN unless new evidence explicitly records otherwise. General modeling, complex cladding features, general Revert/merge, arbitrary code execution and production approval are not implemented.

## Project layout

- `src/RhinoAi.Contracts`: versioned DTOs and detached adapter contracts
- `src/RhinoAi.Core`: validation, exact-preview approval, durable executor journal and execution coordination
- `src/RhinoAi.Host`: real loopback HTTP service and durable Host task journal
- `src/RhinoAi.Plugin`: real Rhino/Eto assembly and UI-thread adapter
- `tests/RhinoAi.Core.Tests`: deterministic fault-injection tests with a fake adapter
- `tests/RhinoAi.Host.IntegrationTests`: real process/HTTP tests without Rhino
- `evidence/`: actual build/test results and explicit acceptance status
- `docs/WORKBUDDY.md`: primary repository-only Windows build/load/live-acceptance runbook
- `scripts/workbuddy-build.ps1` and `scripts/workbuddy-verify.ps1`: native Windows build and per-run evidence verification
- `scripts/release_gate.py`: fail-closed acceptance gate; it never grants engineering production approval

## Runtime and dependency pinning

Build with .NET SDK 8.0.425 (the patch can roll forward within the SDK feature band, as defined in `global.json`). The plugin targets `net8.0-windows`; Host/Core target `net8.0`.

The initial qualification target is Windows Rhino **8.20 running .NET 8**. The official RhinoCommon NuGet feed exposes the 8.20 reference as `8.20.25147.11001-rc`, which is pinned exactly with its transitive Eto reference in `packages.lock.json`. This is an SDK-reference compilation target, not evidence that a Rhino release candidate was executed. Newer Rhino/service-release/runtime combinations need explicit live qualification. .NET Framework, macOS Rhino and Linux Rhino execution are not qualified.

The framework-dependent ASP.NET Host additionally requires Microsoft.AspNetCore.App 8.0 on Windows; Rhino’s embedded runtime alone does not establish that prerequisite. A locally built or cross-built win-x64 apphost is a candidate, not a live Windows qualification.

RhinoCommon/Eto are compile references supplied by Rhino at runtime. This project does not bundle a fake SDK or use Rhino.Compute. The cross-platform Host can run on Linux, but this does not provide a Linux Rhino executor.

## Manual headless verification and historical evidence

For WorkBuddy on Windows, use the native workflow above. For manual build/test diagnostics, from this module root:

```sh
dotnet restore RhinoAi.sln --locked-mode -m:1
dotnet build RhinoAi.sln --no-restore -c Release -m:1
dotnet tests/RhinoAi.Core.Tests/bin/Release/net8.0/RhinoAi.Core.Tests.dll
dotnet tests/RhinoAi.Host.IntegrationTests/bin/Release/net8.0/RhinoAi.Host.IntegrationTests.dll
python3 scripts/test_release_gate.py
python3 scripts/test_workbuddy_evidence.py
```

These commands do not perform live acceptance. Run `workbuddy-verify.ps1` against the corresponding per-run `acceptance.local.json`; it deliberately exits **2 (BLOCKED)** while required live Rhino checks remain `NOT_RUN`/`BLOCKED`. A green build/headless test run must not be relabeled as a complete Stage 1 pass.

`DOTNET=/path/to/dotnet bash scripts/publish-windows.sh` cross-builds the framework-dependent Windows Host and collects the separately built plugin; its separate `packages.win-x64.lock.json` files preserve the normal build locks. Windows execution is still unqualified.

The original `scripts/verify.sh` and `evidence/acceptance.json` belong to the earlier Linux validation workflow; that shell script writes the historical evidence paths and is not the WorkBuddy entry point. Preserve those original reports/logs, including their old source digest and pre-publication statements. Earlier repository-workflow checks remain historical under [evidence/repository-workflow/](evidence/repository-workflow/README.md); its source manifest alone tracks current source bytes, and every Windows run writes its own ignored `artifacts/workbuddy-runs/<run>/` evidence. No historical Linux result establishes current Windows/Rhino execution.

In a read-only-home container, manual checks may set `DOTNET_CLI_HOME`, `NUGET_PACKAGES` and `NUGET_HTTP_CACHE_PATH` to writable temporary directories. No change to the user's machine, network/security settings or account credentials is needed for these cloud checks.

## How to qualify in Rhino

Start with [the Chinese WorkBuddy runbook](docs/WORKBUDDY.md), then consult [the live plugin matrix](src/RhinoAi.Plugin/LIVE-ACCEPTANCE.md) and [Host runbook](docs/host-runbook.md) for implementation details. Install/load only when the user authorizes it on their Windows Rhino workstation. The provided source is not an installer and has not been installed on the user's computer.

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
