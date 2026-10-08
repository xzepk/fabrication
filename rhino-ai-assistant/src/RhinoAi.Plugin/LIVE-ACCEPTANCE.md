# Windows Rhino adapter: implementation candidate and acceptance runbook

Status: **NOT_RUN in live Rhino**. Compiling against the real SDK is not Stage 1 acceptance. This environment is Linux with .NET SDK 8.0.425, without Rhino, a Windows desktop, Rhino native libraries, or a Rhino license. Nothing has been installed on the user's computer or published.

## SDK and runtime baseline

- Windows Rhino 8.20 or newer, explicitly running .NET 8. The plugin rejects other major Rhino or .NET runtime combinations.
- Exact official NuGet SDK: `RhinoCommon 8.20.25147.11001-rc`; Eto/Rhino.UI reference assemblies come from the same McNeel package. NuGet's 8.20 index contains only prerelease reference packages, so this exact actual reference is pinned rather than inventing an unavailable stable version.
- `packages.lock.json` fixes dependency hashes. Use `dotnet restore --locked-mode` before release.
- There are no Rhino SDK stubs and no stand-alone/headless geometric success claims.
- The output intentionally excludes RhinoCommon, Rhino.UI and Eto DLLs: those are loaded from the installed Rhino process.

Primary SDK references:

- [McNeel RhinoCommon 8.20 package](https://www.nuget.org/packages/RhinoCommon/8.20.25147.11001-rc)
- [Rhino .NET runtime guidance](https://www.rhino3d.com/en/docs/guides/netcore/)
- [BeginUndoRecord](https://developer.rhino3d.com/api/rhinocommon/rhino.rhinodoc/beginundorecord)
- [EndUndoRecord](https://developer.rhino3d.com/api/rhinocommon/rhino.rhinodoc/endundorecord)
- [CommonObject JSON serialization](https://developer.rhino3d.com/api/rhinocommon/rhino.runtime.commonobject/tojson)
- [Dockable panels](https://developer.rhino3d.com/api/rhinocommon/rhino.ui.panels/registerpanel)

## Build and load, on an authorized test workstation

Use a throwaway model in a dedicated test directory. Back up existing files first. These are instructions, not evidence that installation has happened.

From the repository module directory:

```powershell
dotnet restore src/RhinoAi.Plugin/RhinoAi.Plugin.csproj --locked-mode
dotnet build src/RhinoAi.Plugin/RhinoAi.Plugin.csproj -c Release --no-restore -m:1
dotnet publish src/RhinoAi.Host/RhinoAi.Host.csproj -c Release -r win-x64 --self-contained false -p:RestoreLockedMode=true -p:NuGetLockFilePath=packages.win-x64.lock.json -o artifacts/host-win-x64
```

Keep `RhinoAi.Plugin.rhp`, `RhinoAi.Core.dll`, `RhinoAi.Contracts.dll`, and the plugin dependency manifest from `src/RhinoAi.Plugin/bin/Release/net8.0-windows/` together. Do not copy McNeel SDK assemblies into that directory.

1. In the test Rhino installation, select .NET 8 using Rhino's supported runtime configuration and restart when requested. Record full Rhino build number and `SystemInfo` output.
2. Load `RhinoAi.Plugin.rhp` through Rhino's plugin manager. Run `RhinoAiPanel` for the dock panel and `RhinoAiFloat` for the separate Eto floating window.
3. Enter/select the separately published `RhinoAi.Host.exe`. Default endpoint is `http://127.0.0.1:47831/`. Click **Start local host**. A shell is never used; an ephemeral random nonce is passed only through the child environment.
4. Alternatively, explicitly start the Host with `RHINOAI_SESSION_NONCE`, `RHINOAI_PORT` and an absolute `RHINOAI_STATE_DIR`; use **Attach host** and enter the nonce in the masked field. The field is cleared immediately and is not persisted or logged. The endpoint must be literal `127.0.0.1` HTTP without credentials, query, fragment or paths.
5. Use an explicit supported unit system and sensible model tolerance, e.g. millimeters / 0.01. Click **Initialize document** once. This explicit modeless action owns a separate Undo record for the persistent document identity. Save a test 3DM to persist that metadata. Inspect/Preview never initializes it implicitly.

## Expected workflow

1. Inspect context. Record document ID, session ID, revision and managed object count.
2. Enter unique `BOX-001`, origin `0, 0, 0`, size `100, 100, 100` (document units).
3. Click **Preview box**. Inspect the blue conduit geometry. No object-table object is added, no attributes are changed, and no model Undo record is opened by Preview.
4. Click **Accept preview & commit**, review the exact summary/document/operation confirmation, then accept. Expect exactly one solid box and one owned semantic Undo record. The pre-operation journal/checkpoint must already be durable and Host Applying acknowledged before entering synchronous Rhino apply.
5. Select exactly that managed box. Set translation `100, 0, 0`, Preview, inspect, accept. Expect the same engineering identity and Rhino GUID, exactly one modified entity, and exact translated geometry.
6. Use native Rhino Undo and then Redo. The adapter observes them, invalidates any preview, and captures actual geometry/identities when next inspected. It never replays a task to counteract native Undo.
7. Save a **managed checkpoint**. Add/move boxes and create an unmanaged Rhino object. Select the checkpoint and **Preview managed restore**. The displayed scope replaces all later managed-object edits, preserves unmanaged objects, and does not reconstruct document tables or the whole 3DM. Accept the dedicated scope confirmation. Expect a new operation, a durable pre-restore checkpoint, and exact saved managed geometry/attributes.
8. Save, close and reopen the test 3DM. Document ID and engineering IDs should survive; session ID must differ and stale old preview commits must fail. Reopened references are reindexed from the actual model.

Both UI surfaces share the same document session, semaphore, Pending plan, operation journal and execution coordinator. Repeated clicks and mixed floating/dock clicks must never apply twice.

## Live acceptance matrix

Every row below remains **NOT_RUN** until observed in Windows Rhino. Fill in actual evidence, build, tester and outcome; do not convert compilation or Core mock-test passes to live passes.

| Row | Procedure | Required observation | Status |
|---|---|---|---|
| L-01 | Load both commands on pinned baseline | Real plugin and both Eto surfaces load; dependencies resolve | NOT_RUN |
| L-02 | Inspect/Preview/Cancel; compare object table and Undo before/after | Detached preview creates zero objects and no implicit document metadata | NOT_RUN |
| L-03 | Accept box, then translate | Exact box dimensions/origin and displacement; count/identity/provenance correct | NOT_RUN |
| L-04 | Click Commit twice and cross-click both UI surfaces | Exactly one mutation and one durable outcome for one operation ID | NOT_RUN |
| L-05 | Change model after Preview: move/delete/copy, units/tolerance, layer/material/linetype/group | Preview clears; stale commit is rejected before mutation | NOT_RUN |
| L-06 | Native Undo then Redo | Real geometry and IDs follow Rhino; revision reconciles; no auto-replay | NOT_RUN |
| L-07 | Save, close, reopen; reopen while Host request pending | Persistent IDs; fresh session; cancellation and cleanup; no old continuation mutates | NOT_RUN |
| L-08 | Native copy of managed box | Duplicate engineering ID blocks further planning; no silent renaming/collapse | NOT_RUN |
| L-09 | Split/join/boolean/trim involving managed boxes, then save/reopen | Unsupported lineage or invalid topology blocks; durable quarantine remains | NOT_RUN |
| L-10 | Restore clean saved checkpoint with later add/move/delete; leave unmanaged object | Exact supported managed snapshot and full attrs restored; unmanaged unchanged | NOT_RUN |
| L-11 | Change checkpoint layer/material table identity/properties; delete a reference | Restore refuses unsupported table reconstruction before mutation | NOT_RUN |
| L-12 | Disable Undo or invoke with existing record | BeginUndoRecord 0 fails before model mutation; never ends another record | NOT_RUN |
| L-13 | Delay Host Applying ACK, click Cancel active request; then queue UI apply and cancel | Pre-mutation cancellation changes no geometry; precise Cancelled journal state | NOT_RUN |
| L-14 | Cancel after synchronous apply begins | Apply/QA/compensation and owned-record closure finish; no partial cancellation | NOT_RUN |
| L-15 | Inject failure after Add/Replace, after attribute change and during QA | Before-image compensation inside owned record; exact verification or FailedRecovery | NOT_RUN |
| L-16 | Make journal disk unwritable before Applying; then after apply | Before-apply failure changes no model; post-apply failure quarantines ambiguity | NOT_RUN |
| L-17 | Kill Host/lose completion ACK after local commit, reconnect and recover ACK | Durable local outcome syncs; zero geometry replay even after native Undo | NOT_RUN |
| L-18 | Crash Rhino between local Applying and terminal journal write | Restart quarantines Applying/FailedRecovery; no automatic replay or false success | NOT_RUN |
| L-19 | Close floating UI or document during delayed preparation/commit | Safe cancellation, deferred store/gate disposal, no callbacks to disposed session | NOT_RUN |
| L-20 | Add unrelated native object while Preview shown | Old preview invalidates; no unrelated Undo or unmanaged replacement | NOT_RUN |

For L-15, L-16 and L-18 use a debugger or dedicated instrumented acceptance build and record the exact breakpoint/fault location. Production UI deliberately does not include arbitrary code execution or destructive fault-injection controls.

## Durable state and limitations

- Executor state: `%LOCALAPPDATA%/RhinoAi/executor/<persistent-document-id>/operations/`. Each operation stores the prepared plan, exact detached before-image checkpoint and eventual outcome/error. The exclusive writer lease prevents two executor processes owning the same document journal.
- Named checkpoints: the sibling `checkpoints` directory. User-requested checkpoints are written with flush and are never promoted to or overwrite the source 3DM.
- Host state: `%LOCALAPPDATA%/RhinoAi/host/` for plugin-launched Host. Executor and Host use different directories/leases.
- Geometry uses the actual Rhino `CommonObject.ToJSON/FromJSON` binary-backed format. Attributes are wrapped with stable layer/material IDs and hashes to prevent restoring stale table indices. Semantic fingerprints omit Rhino object GUID while preserving geometry, attributes/provenance and supported table references.
- Stage 1 managed geometry is a valid solid six-face/eight-vertex Brep marked as a box. It is not an arbitrary Rhino object converter. Groups/custom linetypes and changed/deleted table references are explicit unsupported scope.
- Native topology commands affecting managed entities create a durable lineage quarantine marker. An unsafe lineage/failed-recovery state has **no automatic in-product unlock**. Stop agent edits; inspect journals/checkpoints and the actual model with an authorized operator. Normal Restore requires a clean current snapshot and is not advertised as an escape hatch around quarantine.
- Compensation restores before-images; it never invokes blind global Undo. Compensation is attempted only while the executor still owns its Undo record. Failure to verify compensation or close the owned record is surfaced as recovery-required.
- Rhino GUID restoration uses a matching deleted object when Rhino can undelete it, otherwise adds with the stored GUID and verifies it. Rhino's actual GUID/Undo behavior is a mandatory live acceptance concern, not a compiled guarantee.
- Startup/reopen revision uses a fresh logical-clock epoch; session ID is always new. Native edits are observed and captured from the real model; preview acceptance is bound to document/session/revision/snapshot, never just object name.
- This is a narrow implementation candidate, not V1 release approval, full document versioning, conflict merge, a professional cladding skill, LLM integration or production fabrication authorization.

## Recording results

Save the exact Rhino/.NET/OS versions, build/commit and package lock digest, screenshot of both UI surfaces, scratch 3DM before/after, operation/checkpoint files, fault-injection locations and observed results. Replace NOT_RUN individually only when that row has real evidence. If a row is blocked, state the concrete blocker and leave the release gate blocked.
