# Local Agent Host runbook

Status: implementation candidate, REVIEW. This host does not execute Rhino geometry, run a natural-language model, export files, or grant production approval. The Windows Rhino live acceptance rows in SPEC.md remain NOT_RUN until separately exercised in the pinned environment.

## Components and protocol

- `src/RhinoAi.Host`: real .NET 8 / ASP.NET Core executable, independent process from the Rhino plugin.
- `src/RhinoAi.Core/PlanValidator.cs`: deterministic tool registry and validation for `box.add`, `object.translate`, and `checkpoint.restore`.
- `src/RhinoAi.Contracts/Protocol.cs`: version 1 DTOs shared with the plugin.
- `tests/RhinoAi.Host.IntegrationTests`: executable, dependency-free integration suite. It starts and kills actual HTTP host processes; it is not an in-memory server test.

Only these HTTP routes exist:

| Method | Route | Input | Output |
| --- | --- | --- | --- |
| GET | `/health` | none | protocol, tools, REVIEW status |
| POST | `/v1/prepare` | `PrepareRequest` | `ChangePlan` |
| GET | `/v1/operations/{canonical-uuid}` | none | `OperationRecord` |
| POST | `/v1/complete` | `CompleteRequest` | durable `OperationRecord` |

Every route, including health, requires `Authorization: Bearer <session nonce>`. Responses that reach the application use `ApiError { code, message }` on failure. Invalid HTTP framing rejected before the application by Kestrel may use a transport-level error response.

JSON property names are exact camelCase; unknown properties, duplicate keys, unknown protocol/tools, numeric operation enums, malformed values, and encoded bodies fail closed. The request limit is 1 MiB. There is no arbitrary-code, arbitrary-path export, public network, CORS, browser UI, or LLM endpoint.

## Pairing and startup

The framework-dependent host requires both the .NET 8 runtime and Microsoft.AspNetCore.App on its execution machine, as declared in its generated runtimeconfig.json. Rhino having its own .NET 8 runtime does not establish that the ASP.NET Core runtime is installed. A separately built and qualified self-contained Windows host is an alternative packaging choice; no Windows packaging/runtime installation has been performed or verified by the Linux tests.

The Rhino plugin's `AgentHostClient.StartAsync` starts the separate Windows host executable with a fresh cryptographically random 32-byte base64url nonce passed only in the child's private `ProcessStartInfo.Environment`.

Configuration is environment-only; command-line arguments are rejected:

| Variable | Requirement |
| --- | --- |
| `RHINOAI_SESSION_NONCE` | required; random base64url, 32–256 ASCII characters. Generate 32 random bytes, encode URL-safe base64, omit padding. Never place it in a command, file, URL, report, or log. |
| `RHINOAI_PORT` | optional, default `47831`; integer 1024–65535. Select a different port for another paired host. |
| `RHINOAI_STATE_DIR` | optional absolute directory; default is the current user's LocalApplicationData/RhinoAi/HostJournal. Keep the directory stable across host restarts to retain records. |

The listener is programmed as literal IPv4 loopback `127.0.0.1`; environment configuration such as `ASPNETCORE_URLS` cannot override it. Use `http://127.0.0.1:<port>/`. Host headers must use `127.0.0.1` or `localhost` and the actual port. Any Origin header is rejected, even with a correct nonce. The nonce is removed from the host's inherited environment after reading it, remains only in process memory, and changes with each new pairing.

This protects against accidental network exposure, browser-origin requests and unauthenticated local clients. It does not protect against a compromised same-user process or administrator capable of reading process memory. Do not reuse the nonce as an account password or long-lived credential. No credential/configuration installation is required or performed.

Use a different directory for the plugin's execution ledger and host journal. One host process owns its journal directory through an exclusive lease. A second writer fails startup. An invalid or unsupported persisted journal fails startup rather than resetting state.

## Lifecycle and acknowledgement rules

1. The plugin captures detached context on the Rhino UI thread and POSTs prepare.
2. Host validates the exact structured tool and context, writes the request/plan/before checkpoint plus task `Review` state, then returns the plan.
3. The plugin displays detached Preview. Accepted Preview is required before any mutation.
4. The plugin durably stores its local before-images and `Applying` record, POSTs complete with `Applying`, and waits for the host's durable acknowledgement before UI-thread mutation.
5. The plugin revalidates the actual document, serializes writes, owns a native Undo record, applies and verifies synchronously, then durably saves its local verified result.
6. POST complete with `Committed` carries that saved outcome. Host checks session, revision, identities, effect arrays, untouched objects, and restore-target equivalence before saving/acknowledging it.
7. On a lost ACK, GET the operation and resend the already durable outcome as needed. Never assume an HTTP error proves no Rhino mutation occurred.

Host operation states are independent of persisted task states. A task aggregates its operations: any recovery failure gives `Failed`; otherwise any Applying gives `Running`, any Prepared gives `Review`, a completed task with committed effects gives `Committed`, and all-cancelled/rejected work gives `Cancelled`. Production review status remains REVIEW regardless of an operation's committed state.

The same operation ID and canonical request hash returns the existing plan/outcome without a second journal transition. Changing the payload or completion under that ID is a conflict. Although UUIDs are document/task scoped conceptually, this foundation additionally rejects reusing a UUID across different document/task scopes. GET exposes the authoritative host status before the client decides whether any action is permitted.

Allowed completion transitions:

- Prepared → Applying, Cancelled, or Rejected
- Applying → Committed or FailedRecovery
- Applying → Cancelled only for the authenticated plugin's durably established non-mutation result, with no outcome and the exact marker `Cancelled before document mutation.`
- After restart, FailedRecovery → Committed may reconcile the paired plugin's already durable same-hash verified completion. FailedRecovery → Cancelled requires the same proven non-mutation marker. Neither transition performs or authorizes a geometry replay.
- Same-state replay must carry an identical outcome/error. Other terminal transitions are denied.

Only one operation may be Applying for a document. A stored FailedRecovery blocks new plans and new Applying transitions for that document. There is not yet an audited general recovery-clear endpoint for a genuine partial-effect failure. Such a failure remains blocked pending explicit reconciliation design and live acceptance; do not edit or delete the journal to manufacture a success or automatically run a new Restore. A normal accepted checkpoint Restore is supported for a non-quarantined document.

## Persistence and failures

`journal-v1.json` holds the operations and task records as a single image. Updates write a new temporary file with WriteThrough and Flush(true), then atomically replace the current image. This is a replacement journal, not an append-only log. Before-checkpoint snapshots are metadata/serialized managed geometry supplied by the plugin; they do not claim to be a full saved 3DM.

Process restart preserves Prepared and terminal records. Any interrupted Applying becomes FailedRecovery before the listener starts. It never automatically re-executes. A storage failure returns 503 and quarantines the running host, including health, so the plugin cannot proceed under a false durability acknowledgement.

Filesystem flush/atomic replacement addresses ordinary process-crash recovery; power-loss durability depends on the OS/filesystem/storage. Native Rhino Undo is not a database transaction. HTTP tests cannot prove geometric effect, Undo/Redo, save/reopen, visual Preview, or compensation correctness in Rhino.

## Build and verify

From this module root, using the pinned SDK 8.0.425:

```sh
export DOTNET=/workspace/shared/dotnet-runtime/dotnet
export DOTNET_CLI_HOME=/tmp/rhinoai-dotnet-home
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export MSBuildEnableWorkloadResolver=false
"$DOTNET" build src/RhinoAi.Host/RhinoAi.Host.csproj -c Release -m:1
"$DOTNET" build tests/RhinoAi.Host.IntegrationTests/RhinoAi.Host.IntegrationTests.csproj -c Release -m:1
"$DOTNET" tests/RhinoAi.Host.IntegrationTests/bin/Release/net8.0/RhinoAi.Host.IntegrationTests.dll
```

Use your actual installed SDK path on Windows; the Linux path above describes the verified implementation workspace, not a user-machine installation step. The test executable accepts optional `<dotnet-executable> <host-dll> [evidence-directory]` arguments. With no arguments it locates the matching Debug/Release host binary and current dotnet process.

Evidence is written to `artifacts/host-integration/results.json`, including per-test outcomes, environment/runtime, host binary SHA-256, and an explicit live-Rhino NOT_RUN statement. Tests cover authentication, Origin/Host guards, payload limits, strict schemas, duplicate requests, invalid transitions, concurrent apply, lost ACK, restart/quarantine/reconciliation, Restore persistence, corrupt journals, exclusive ownership, and storage failure. The overall module verification script additionally builds the real plugin and runs Core tests; see the final verification report for the exact executed count and source hashes.
