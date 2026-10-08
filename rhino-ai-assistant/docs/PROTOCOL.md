# Local IPC and execution contract

The executable DTO source is `src/RhinoAi.Contracts/Protocol.cs`; strict Host decoding and deterministic validation are authoritative. Protocol version is `1`. Unsupported fields, tools and non-finite values are rejected.

## Request lifecycle

1. The plugin captures a detached snapshot on the Rhino UI thread. Expected context binds document ID, fresh session ID, revision and snapshot hash.
2. The Host validates `POST /v1/prepare` and durably persists the prepared task before returning a typed `ChangePlan`.
3. The plugin validates the same plan, journals `Prepared`, and displays detached preview geometry. Switching preview changes the accepted operation binding.
4. On explicit Apply, the coordinator captures a before-checkpoint and durably writes `Applying`. It sends Host `Applying` outside any Undo record.
5. After that asynchronous boundary and any UI queue delay, context and cancellation are rechecked on the UI thread immediately before the synchronous adapter operation.
6. The adapter owns one nonzero Undo record, applies and verifies actual effects, compensates from detached before-images when possible, then closes its record. No network, user wait or LLM work occurs within it.
7. The executor durably writes the verified outcome before acknowledging. The Host records `Committed`. Same operation/hash replay returns the saved result without mutating Rhino again, even after native Undo.

## Cancellation and ambiguity

Cancellation before synchronous mutation begins leaves geometry unchanged. During the synchronous mutation, cancellation is deferred until its verified result or explicit failure is known. A known cancellation record uses `Cancelled before document mutation.` so Host acknowledgement can safely reconcile a previously marked Applying task.

If the outcome cannot be established, use `FailedRecovery`/quarantined `Applying`, preserve before-images and actual model, and block automatic retry. No timeout is permission to reapply.

## Checkpoint restore

`checkpoint.restore` includes an explicit `CheckpointId` and a matching `RestoreTarget`; its request hash binds the entire checkpoint payload. It shares the same prepared/applying/committed pipeline, exact-preview requirement and pre-restore checkpoint. The only supported scope is `managed-objects` within the same document and compatible units/tolerance. Unmanaged Rhino objects are outside that replacement scope.

## Identity

EngineeringEntityId is the business key; RhinoId is an instance identifier. Geometry and semantic attributes produce a fingerprint independent of RhinoId. Object metadata persists with the 3DM; copied metadata creates a detectable collision. Split/join/boolean lineage is not implemented and must block affected unsupported workflows.

## Local security

The Host binds an explicit IPv4 loopback address. A random ephemeral session nonce travels in child-process environment, then authenticates HTTP requests. It is not persisted, included in task data, or printed in logs. Origin-bearing browser requests, unapproved hostnames, remote clients, oversize requests, unknown operations and arbitrary-code execution are rejected. No persistent access grant is created.


## Stage 2 versioned local workflows

- `GET /v2/capabilities`: authenticated read-only planner/Skill capability discovery, configuration status and explicit limits.
- `POST /v2/plan`: `PlannerRequest` -> `PlannerResponse`, plannerVersion=2. One optional local-model call, one grounded decision; no journal or Rhino mutation.
- `POST /v2/plan/validate`: `PlannerValidationRequest` -> the same response for external-agent compatibility, with no model call or mutation.
- `POST /v2/cladding/review`: `CladdingReviewRequest` -> immutable `CladdingReviewResult`, using existing tool protocolVersion=1. The URI version and the independent planning contract version do not renumber old journals.
- `GET /v2/cladding/reviews/{canonical-uuid}`: revalidate and retrieve a completed immutable review. A failed/partial job is never returned as successful.
- Existing `POST /v1/prepare` supports `cladding.plates.add` with exact bounded `Plates` and `Provenance`. Host resolves the trusted job and rehashes current artifacts rather than trusting caller-supplied hashes. Before recording `Applying`, it repeats trusted job validation.

The optional new tool fields are omitted when null so historical Stage 1 request hashes remain stable. Unknown fields, malformed values, unsupported geometry and source mismatches still fail closed. Selected-source attestations come from the Rhino UI-thread adapter after exact supported-shape validation; a language model cannot establish geometry validity.

Cladding contract details are in `src/RhinoAi.Contracts/CladdingContracts.cs`, with the published capability manifest/schema under `adapters/cladding/`. Every job binds request and document snapshot, source/fingerprint/provenance, design/measured/used values, Skill/rule version/source, preview and complete artifact hashes. Only explicit reviewed engineering inputs are executed. Manufacturing release remains false.

See [Stage 2 local self-use](STAGE2-LOCAL.md) for configuration and bounds. Real local-model and Windows/Rhino qualification remain separate NOT_RUN gates until actually exercised.
