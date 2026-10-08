# Rhino AI Agent Harness — Product & Technical Specification

> Status: Implementation baseline; production release blocked until stage gates pass  
> Version: 0.2  
> Updated: 2026-10-08; based on upstream commit `9561a0b929f9191e66230196d1be1d7453115aff`  
> Target: Rhino 8 / Windows first  
> Repository module: `rhino-ai-assistant/`

---

## 1. Purpose

Build an extensible AI Agent Harness inside Rhino that allows users to understand, modify, review, compare, revert, and automate Rhino engineering workflows through natural language.

The product MUST NOT be designed as a one-off “AI chat plugin” or as a hard-coded cladding tool.

The system SHALL provide a reusable agent runtime for multiple Rhino/AEC workflows, including but not limited to:

- general Rhino modeling;
- cladding / envelope detailing;
- curtain-wall detailing;
- steel detailing;
- quantity takeoff;
- drawing review;
- model QA;
- drawing / annotation generation;
- Grasshopper workflow execution;
- future engineering Skills.

`cladding-delivery` is the first professional Engineering Skill integrated into the Harness, not a component that defines the Harness architecture.

---

# 2. Product Positioning

## 2.1 One-line definition

**Rhino AI Agent Harness is a controlled AI execution layer for Rhino: natural language becomes structured Tool/Skill execution, and every material model change is previewable, traceable, reversible, and versioned.**

## 2.2 Core product value

The product is not primarily valuable because “AI can draw”.

Its core value is:

- Understandable
- Executable
- Reviewable
- Reversible
- Comparable
- Auditable
- Extensible

The long-term product direction is a **Rhino AI Engineering Platform**, not a chatbot embedded in CAD.

---

# 3. Non-goals

V1 MUST NOT attempt to:

- make the LLM a geometric source of truth;
- expose arbitrary RhinoCommon APIs directly to the model;
- execute arbitrary LLM-generated Python in the Rhino process by default;
- implement all Rhino commands;
- implement all engineering domains in one plugin;
- silently modify files or overwrite external production deliverables;
- equate successful code execution with engineering approval;
- embed all LLM / workflow / Skill logic inside the Rhino plugin;
- use Rhino GUIDs as persistent engineering entity IDs;
- save a full 3DM snapshot for every small change.

---

# 4. Architectural Principles

## 4.1 LLM plans; deterministic tools execute

Primary path:

```text
Natural Language
      ↓
Intent / Planner
      ↓
Structured Tool Call / Skill Call
      ↓
Schema + Policy Validation
      ↓
Preview / Execution
      ↓
Rhino Executor
      ↓
ChangeSet
      ↓
Commit
```

The following MUST NOT be the default path:

```text
Prompt → LLM-generated Python → exec() → Rhino
```

Code generation MAY exist as an expert mode, but it SHALL be isolated and permissioned.

---

## 4.2 Tool and Skill are separate abstractions

### Tool

A Tool is a small, deterministic, schema-defined capability.

Examples:

```text
scene.get_selection
curve.offset
surface.split
brep.boolean
object.move
layer.create
view.capture
document.export
```

A Tool answers:

> How do I operate Rhino?

### Skill

A Skill is a reusable domain workflow composed from tools, deterministic algorithms, references, rules, and tests.

Examples:

```text
cladding-delivery
curtain-wall
steel-detailing
quantity-takeoff
drawing-review
model-qa
drawing-generation
```

A Skill answers:

> How do I complete an engineering task?

A Skill MAY call:

- Rhino Tools;
- external deterministic services;
- OCCT/CadQuery;
- ACadSharp;
- internal scripts;
- other Skills when explicitly supported.

---

## 4.3 Plugin and Agent Host MUST be separated

The Rhino plugin SHALL stay relatively thin.

### Rhino Plugin responsibilities

- UI;
- active Rhino document integration;
- selection context;
- viewport capture;
- Rhino Tool execution;
- UI-thread dispatch;
- preview rendering;
- Undo transactions;
- model change observation;
- ChangeSet collection;
- interaction with local Agent Host.

### Agent Host responsibilities

- LLM Gateway;
- Agent runtime;
- task planning;
- Tool Registry;
- Skill Registry;
- task state;
- context composition;
- permission/policy evaluation;
- code sandbox;
- version metadata;
- project metadata;
- evaluation;
- optional remote/cloud integration.

This separation is required so the same Agent Host can later support other CAD hosts.

---

# 5. High-Level Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                       Rhino Desktop                         │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Rhino AI Plugin                                      │  │
│  │                                                      │  │
│  │ Floating Assistant / Dock Panel                     │  │
│  │ Chat | Tasks | Changes | Skills                     │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                  │
│                     Rhino Bridge                           │
│                         │                                  │
│        ┌────────────────┼─────────────────┐                │
│        ▼                ▼                 ▼                │
│ Context Collector   Tool Executor    Change Tracker        │
│        │                │                 │                │
│        │           RhinoCommon            │                │
│        └──────────── RhinoDoc ─────────────┘                │
│                         │                                  │
│                      3D Model                              │
└─────────────────────────┬──────────────────────────────────┘
                          │
                  WebSocket / HTTP
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                       Agent Host                            │
│                                                            │
│ Agent Runtime                                              │
│ ├── Intent / Planner                                       │
│ ├── Tool Registry                                          │
│ ├── Skill Registry                                         │
│ ├── Context Manager                                        │
│ ├── Policy / Permission                                    │
│ ├── Task State                                             │
│ └── Evaluation                                             │
│                                                            │
│ Code Sandbox     Version Store      Project Store           │
│ Skill Runtime    Artifact Store     LLM Gateway             │
└──────────────┬─────────────────────────────────────────────┘
               │
        OpenAI / DeepSeek /
        Local Model / etc.
```

---

# 6. Deployment Strategy

## 6.1 V1 — Local-first

Target:

```text
Windows Workstation
├── Rhino 8
├── Rhino AI Plugin
└── Local Agent Host
```

Communication SHALL default to localhost.

This minimizes infrastructure dependency and allows fast iteration.

## 6.2 Enterprise evolution

Future:

```text
Windows Rhino
    │
Local Bridge
    │
    ▼
Linux Agent Platform
├── LLM Gateway
├── Skill Runtime
├── Project Service
├── Version Metadata
├── Artifact Store
└── Evaluation
```

The V1 protocol MUST NOT prevent this migration.

---

# 7. Rhino Plugin

## 7.1 Recommended stack

- C#
- .NET 8; Windows Rhino 8.20 or later running the .NET 8 runtime; pinned RhinoCommon 8.20 reference package (exact package version in project/lock files). Newer runtime combinations require explicit live qualification; no .NET Framework compatibility claim.
- RhinoCommon
- Eto.Forms
- optional WebView for modern chat UI

## 7.2 UI modes

The product SHOULD expose three UI densities:

### Mini Floating Assistant

Small always-available entry point.

### Expanded Floating Chat

For quick Ask/Edit tasks.

### Full Dock Panel

Tabs:

```text
Chat | Task | Changes | Skills
```

Potential later tabs:

```text
Branches | Artifacts | Evaluation
```

---

# 8. User Interaction Modes

## 8.1 Ask

Read-only.

Examples:

- “What are these selected objects?”
- “What is the panel area?”
- “Why are these objects not aligned?”
- “Summarize the current layer structure.”

No model mutation.

## 8.2 Edit

Short reversible tasks.

Examples:

- move selected objects;
- assign layer;
- offset surface;
- rename / number panels;
- modify attributes.

Typical execution:

```text
Plan → Execute → ChangeSet → Commit
```

## 8.3 Agent

Multi-step tasks.

Examples:

- build a canopy cladding model;
- detail a curtain-wall zone;
- perform model QA and repair;
- create panelization + BOM.

Agent MUST expose task status and allow interruption.

## 8.4 Code

Expert mode only.

Flow:

```text
Prompt
  ↓
Generate Python / C#
  ↓
Static Inspection
  ↓
Sandbox Validation
  ↓
Explicit Approval
  ↓
Controlled Rhino Execution
```

The Rhino plugin MUST NOT execute raw LLM output via unrestricted `exec()`.

---

# 9. Agent Task State Model

Long-running tasks SHALL use a persistent state machine.

Minimum states:

```text
PLANNING
RUNNING
WAITING_USER
REVIEW
COMMITTED
FAILED
CANCELLED
REVERTED
```

A task SHOULD expose:

- task ID;
- user request;
- current plan;
- completed steps;
- active step;
- pending user decision;
- Tool Calls;
- generated ChangeSets;
- artifacts;
- error state.

Example:

```text
T-102  Canopy cladding

✓ Analyze structure
✓ Build reference envelope
● Panelize
○ Number panels
○ Unfold
○ BOM
○ Order drawings
```

---

# 10. Tool Registry

## 10.1 Tool contract

Every Tool MUST define:

- stable Tool ID;
- description;
- JSON input schema;
- output schema;
- read/write classification;
- risk level;
- preview capability;
- undo capability;
- timeout;
- audit policy;
- allowed object/entity scope.

The LLM MUST call Tools through structured arguments.

## 10.2 Initial Tool categories

### Context

```text
scene.get_document
scene.get_units
scene.get_layers
scene.get_selection
scene.get_objects
scene.get_object
scene.get_bbox

view.get_active
view.capture
```

### Geometry

```text
curve.create
curve.join
curve.offset
curve.project

surface.create
surface.offset
surface.split

brep.boolean
brep.intersect
brep.section
brep.measure
```

### Objects

```text
object.add
object.delete
object.copy
object.move
object.rotate
object.transform
object.set_attributes
```

### Layers

```text
layer.create
layer.rename
layer.set_attributes
layer.move_objects
```

### Document

```text
document.save
document.save_copy
document.export
```

### Annotation

```text
dimension.create
text.create
leader.create
```

### Engineering utilities

```text
geometry.distance
geometry.angle
geometry.area
geometry.volume
geometry.curvature
```

The catalog above is a roadmap, not a V1 tool-count commitment. Stage 1 SHALL prove a narrow, dependable vertical slice before expanding tools. Stage 1 initially supports context inspection, box creation/translation, Preview/Commit, checkpoint and recovery commands. Unsupported tools fail explicitly.

---

# 11. Rhino Execution Model

## 11.1 UI-thread execution

Agent/HTTP work MAY run asynchronously.

All live Rhino document reads, reference resolution, geometry duplication, and mutations MUST run on the Rhino UI thread. Background calculation MUST use detached immutable snapshots or independently duplicated geometry only. Apply is serialized per document and revalidates the document/session/revision/object expectations immediately before mutation. See section 42.

Conceptual flow:

```text
Agent Thread
   ↓
Execution Queue
   ↓
Rhino UI Thread
   ↓
Undo Transaction
   ↓
RhinoDoc
```

## 11.2 Transaction boundary

One user-meaningful Agent operation SHALL be wrapped as one Rhino Undo transaction where practical.

Example:

```text
"Panelize selected canopy"
    ↓
12 Rhino operations
    ↓
1 Undo transaction
    ↓
1 ChangeSet
    ↓
1 Commit
```

The system SHOULD avoid making every atomic Rhino API call a separate user-visible transaction.

---

# 12. Risk-Based Execution Policy

The product SHOULD minimize repetitive confirmation.

## R0 — Read-only

Examples:

- inspect;
- calculate;
- capture screenshot;
- read layers.

Policy: auto-execute.

## R1 — Reversible Edit

Examples:

- add objects;
- move;
- change layer;
- number panels;
- modify attributes.

Policy: bounded reversible edits may auto-execute only with explicit configured permission. Stage 1 always requires an accepted Preview. Undo does not provide database atomicity or durable rollback; see section 43.

## R2 — Structural Change

Examples:

- repanelization;
- mass replacement;
- large-scale deletion;
- major geometry rebuild.

Policy: Preview required before applying in V1. Any later configurable trusted-operation exception requires an explicit revised policy and its own acceptance evidence.

## R3 — External / Irreversible

Examples:

- overwrite file;
- export official production deliverable;
- send/upload artifact;
- issue order.

Policy: explicit confirmation required.

Risk classification MUST be part of the Tool definition, not improvised only by the LLM.

---

# 13. Preview System

R2 changes MUST support an interactive model preview. Stage 1 also requires Preview for R1 mutations. Preview is detached/non-authoritative, bound to a document session and revision, and invalidated on any relevant edit, undo/redo, close/reopen, or identity collision.

Recommended representation:

```text
Existing     neutral
Added        positive highlight
Modified     warning highlight
Deleted      translucent negative highlight
```

Preview MUST show a structured summary:

```text
+ 84 objects
~  7 objects
- 31 objects
```

For engineering Skills, Preview SHOULD additionally show domain impact:

- panel count;
- area;
- material;
- BOM delta;
- nesting delta;
- affected drawings;
- warnings.

Preview objects SHOULD NOT become authoritative engineering objects until committed.

---

# 14. Context System

The whole 3DM file MUST NOT be sent to the LLM by default.

A task-scoped `SceneContext` SHALL be constructed.

Example:

```json
{
  "document": {
    "units": "mm",
    "absolute_tolerance": 0.01
  },
  "selection": [
    {
      "engineering_id": "PANEL-P001",
      "rhino_guid": "...",
      "type": "Brep",
      "layer": "AL-PANEL",
      "bbox_mm": [1450, 2400, 30],
      "area_mm2": 3480000
    }
  ],
  "view": {
    "name": "Perspective"
  }
}
```

Context Manager responsibilities:

- collect relevant selection;
- collect model metadata;
- reduce unnecessary geometry;
- resolve Engineering IDs;
- expose dimensions and geometry metrics;
- capture viewport only when useful;
- avoid transferring unrelated model content.

---

# 15. Multimodal Analysis

Vision SHALL supplement deterministic geometry, not replace it.

Recommended pattern:

```text
Viewport Screenshot
+
Selected Object Metadata
+
Geometry Metrics
+
Engineering Context
     ↓
Vision / LLM reasoning
     ↓
Deterministic geometry check
```

Example:

AI visually suspects inconsistent joint width.

Then call:

```text
geometry.distance
```

and report exact values.

---

# 16. Engineering Entity Identity

Rhino object GUID MUST NOT be the persistent engineering identity.

Each managed engineering object SHALL have a stable `EngineeringEntityId`.

Example:

```text
EngineeringEntityId = PANEL-P001
```

It MAY be stored in Rhino object user metadata:

```text
AI_ENTITY_ID=PANEL-P001
```

Object replacement may change the Rhino GUID while preserving Engineering ID:

```text
Rhino GUID A
      ↓
PANEL-P001
      ↓
Rhino GUID B
```

This identity layer is required for:

- BOM;
- field survey;
- order drawings;
- ChangeSet diff;
- version restore;
- cross-run comparison;
- engineering audit.

---

# 17. Change Tracking

The plugin SHOULD observe both Agent and human model mutations.

Relevant change categories include:

- Add object;
- Delete object;
- Replace object;
- Modify attributes;
- layer changes;
- material changes;
- document metadata changes where relevant.

Version history SHOULD distinguish actor/source:

```text
AI
Human
Survey
Import
External Skill
```

Example:

```text
C031  AI      Repanelize canopy
C032  Human   Manually adjust P034
C033  AI      Renumber affected panels
C034  Survey  Apply field measurements
```

---

# 18. Git-like Version Model

Versioning is a V1 core feature, not a later add-on.

## 18.1 Three logical states

```text
Working Model
    ↓
ChangeSet
    ↓
Commit Graph
```

## 18.2 Working Model

Human and AI edits MAY accumulate before a semantic Commit.

The UI SHOULD expose:

```text
7 uncommitted changes

+3 objects
~4 objects

[Commit]
[Discard]
```

Agent tasks SHOULD normally create one semantic ChangeSet for one task rather than one commit per Rhino command.

---

# 19. ChangeSet Contract

Minimum fields:

```json
{
  "change_set_id": "CS-0023",
  "task_id": "T-0102",
  "actor": "AI",
  "prompt": "...",
  "plan": [],
  "tool_calls": [],
  "added": [],
  "modified": [],
  "deleted": [],
  "engineering_parameters": {},
  "before_state_refs": [],
  "after_state_refs": [],
  "artifacts": [],
  "skill_versions": {},
  "created_at": "..."
}
```

A ChangeSet MUST contain sufficient information to:

- explain what changed;
- reconstruct affected object state when supported;
- create a Commit;
- calculate engineering impact;
- support comparison.

---

# 20. Commit Model

A Commit is an accepted semantic state transition.

Example:

```text
C023
"Canopy repanelized to max width 1200 mm"

+42 panels
~ 6 references
-38 previous panels

max_width_mm:
1500 → 1200
```

Commit metadata SHOULD include:

- parent commit(s);
- ChangeSet;
- actor;
- timestamp;
- task;
- Skill versions;
- Tool versions where material;
- Rhino version;
- engineering rule version;
- relevant input hashes;
- artifact references.

---

# 21. Undo, Revert and Restore

These operations have different semantics.

## 21.1 Undo

Use Rhino native Undo for immediate short-term reversal.

Use case:

> Undo the operation I just ran.

## 21.2 Revert Commit

Create a new Commit that inverses an older Commit. Any V1 Revert support is limited to conflict-free task-local inversion when all affected objects still match the recorded after-images. Overlapping later edits, uncertain identity, and missing before-images MUST block Revert; general semantic merge is deferred.

History remains intact.

```text
C003  Panelization
C004  Numbering
C005  Revert C003
```

Preferred for engineering audit.

## 21.3 Restore / Checkout

Restore the model/project to a specific historical state.

Use case:

> Restore the model to the field-survey milestone.

Restore MUST be explicit and create a traceable event/commit instead of silently deleting history. Its UI MUST identify exact scope and all later human/AI edits that will be replaced. A pre-restore durable checkpoint is mandatory. Stage 1 restores the explicitly declared supported managed-object scope; full-document file replacement, arbitrary historical reconstruction, and conflict merge are not implied. Unmanaged objects remain outside that scoped restore. Full 3DM checkpoint files are separate recovery artifacts and never silently overwrite the user source file.

---

# 22. Branches / Design Alternatives

The version model SHOULD support alternate design branches after the V1 core is stable.

Example:

```text
                 ┌─ A: 1500 mm panels
M010 ────────────┤
                 ├─ B: 1200 mm panels
                 └─ C: grid-based panels
```

The product SHOULD eventually support engineering comparison:

| Metric | A | B | C |
|---|---:|---:|---:|
| panel count | 84 | 112 | 91 |
| stock sheets | 37 | 35 | 36 |
| utilization | 82% | 88% | 85% |
| joint length | 216m | 294m | 238m |

Branching turns version control into a design exploration mechanism.

Branching is Stage 3 only, after V1 release gates pass; it MUST NOT displace foundational validation.

---

# 23. Milestones

A Milestone is a formal engineering checkpoint, not every edit.

Examples:

```text
M01 Concept model approved
M02 Detailing scheme approved
M03 Field survey version
M04 Order version
M05 As-built version
```

Relationship:

```text
Commit = working history
Milestone = engineering checkpoint
```

Creating a Milestone SHOULD trigger a full checkpoint and stronger validation.

---

# 24. Version Storage

Do not store a full 3DM for every Commit.

Recommended strategy:

```text
Full Checkpoint + Object Delta
```

Example:

```text
M010    full 3DM
C011    delta
C012    delta
C013    delta
M020    full 3DM
```

Create a full checkpoint when:

- a Milestone is created;
- delta chain is too long;
- affected geometry exceeds a threshold;
- before official export/order;
- user explicitly requests snapshot.

---

# 25. Git Usage

Git MAY be used for text/structured project state.

Recommended Git-managed content:

```text
project/
├── engineering/
│   ├── components.json
│   ├── rules.yaml
│   └── survey.yaml
├── changes/
├── commits/
├── skills.lock
└── milestones/
```

Large artifacts such as:

- 3DM;
- STEP;
- meshes;
- previews;
- generated drawings;

SHOULD be stored in:

- artifact/object storage; or
- Git LFS when appropriate.

Plain Git SHOULD NOT become the primary binary geometry database.

---

# 26. Skill System

## 26.1 Skill package contract

A Skill SHOULD contain:

```text
Skill
├── SKILL.md
├── Input Schema
├── Output Schema
├── Required Tools
├── Workflow
├── Rules
├── Scripts
├── References
└── Tests
```

## 26.2 Skill discovery

Agent Host SHALL maintain a Skill Registry.

The Agent SHOULD select Skills based on user intent and task context.

Example:

```text
"Detail this canopy with aluminum cladding"
→ cladding-delivery
```

```text
"Check this façade model for obvious problems"
→ model-qa
```

Skills SHALL NOT require changes to the core Agent runtime merely to become discoverable.

---

# 27. Initial Professional Skill: cladding-delivery

Existing `cladding-delivery/` SHALL be integrated as the first professional Skill.

Harness responsibilities:

- expose Rhino selection and geometry;
- show previews;
- apply accepted geometry to Rhino;
- show task status;
- create ChangeSet / Commit;
- allow manual engineering edits.

Skill responsibilities:

- DWG/engineering interpretation;
- canonical engineering schema;
- cladding rules;
- panelization;
- survey overlay;
- panel IDs;
- unfold;
- BOM;
- nesting;
- order data;
- QA.

The Harness MUST NOT embed cladding-specific logic into the generic Tool layer.

---

# 28. Code Sandbox

Generated code MUST be separated from Rhino’s unrestricted main process.

Default sandbox permissions SHOULD deny:

- unrestricted filesystem;
- unrestricted network;
- shell execution;
- process spawning;
- registry access;
- arbitrary secrets.

When code needs Rhino mutation:

1. Generate;
2. inspect;
3. sandbox-test where possible;
4. request permission based on risk;
5. execute via controlled Rhino bridge;
6. wrap in Undo + ChangeSet.

---

# 29. Protocol Between Plugin and Agent Host

V1 protocol SHOULD support:

### Plugin → Host

- session open/close;
- user message;
- context snapshot;
- selected entity metadata;
- viewport image reference;
- task action;
- approval/rejection;
- ChangeSet outcome;
- Tool execution result.

### Host → Plugin

- assistant message;
- task plan;
- Tool execution request;
- Preview request;
- Skill invocation;
- approval request;
- task status update;
- commit metadata;
- restore/revert request.

Transport recommendation:

- localhost HTTP for request/response;
- WebSocket for task progress/events.

Protocol payloads MUST be versioned.

---

# 30. Security and Permission Model

At minimum:

- never expose raw model-independent arbitrary API execution to the LLM;
- validate all Tool args against schema;
- enforce risk policy outside the LLM;
- restrict document/export paths;
- record destructive actions;
- require explicit approval for R3;
- never place commercial license secrets in Skills;
- separate external service credentials from UI/model context;
- do not leak unrelated model/project data into prompts.

---

# 31. Observability and Audit

For every Agent task capture:

- task ID;
- prompt;
- model/provider;
- plan;
- context summary;
- Tools called;
- arguments;
- results;
- timings;
- failures/retries;
- user approvals;
- ChangeSets;
- Commits;
- Skill versions;
- generated artifacts.

Sensitive prompt/context content SHOULD support redaction policy.

---

# 32. Evaluation

V1 MUST include automated regression, minimal deterministic model QA, and a fail-closed release gate. Visual impression is not an acceptance test. See sections 45–46.

Suggested dimensions:

- Tool selection correctness;
- parameter correctness;
- invalid Tool Call rate;
- geometry success rate;
- Undo success;
- Revert/Restore correctness;
- ChangeSet completeness;
- engineering Skill task success;
- user intervention count;
- task completion time;
- unsupported-case detection.

Engineering Skills SHOULD define Golden Cases.

---

# 33. Repository Structure

Recommended initial monorepo layout:

```text
fabrication/
│
├── rhino-ai-assistant/
│   ├── SPEC.md
│   ├── plugin/
│   │   ├── RhinoAi.Plugin/
│   │   ├── RhinoAi.UI/
│   │   ├── RhinoAi.Tools/
│   │   └── RhinoAi.ChangeTracking/
│   │
│   ├── agent-host/
│   │   ├── runtime/
│   │   ├── planner/
│   │   ├── context/
│   │   ├── skills/
│   │   ├── versioning/
│   │   └── sandbox/
│   │
│   ├── protocol/
│   └── tests/
│
├── cladding-delivery/
└── other-skills/
```

The exact code layout may evolve, but Plugin, Host, Protocol, Versioning and Skills boundaries MUST remain explicit.

---

# 34. Staged Delivery Scope (replaces monolithic MVP)

V1 is the combined result of Stages 1 and 2, released only after their acceptance gates. Completing code compilation or headless tests alone does not complete Stage 1. The original broad catalog remains roadmap material.

## 34.1 Stage 1 — Dependable foundational vertical slice

Outcome: a compilable Rhino 8 Windows plugin plus a separate local .NET Agent Host with versioned HTTP IPC and persistent task state, proving:

`detached context → plan → Preview → accepted Commit → Undo/Redo → save/reopen → checkpoint Restore`.

Required:
- Eto floating window and dockable panel entry points; task/change/status and explicit Preview/Apply/Reject controls.
- Small deterministic tool registry; first executable operations are box creation and translation of supported managed objects. No arbitrary code endpoint.
- UI-thread snapshot/apply adapter, detached viewport preview, serialized writes, context and object preconditions, bounded cancellation.
- Stable document ID, fresh reopen/session ID, monotonically reconciled revision; engineering identity separate from Rhino GUID.
- Durable task/operation journal, before-images/checkpoints, operation-ID and payload-hash deduplication, lost-ACK recovery, honest ambiguous-state quarantine.
- One owned Undo record for a meaningful task; native Undo/Redo observation and save/reopen reconciliation.
- Managed-scope checkpoint Restore with displayed replacement scope and preserved unmanaged objects; task-local no-conflict Revert may be added only with the same safeguards.
- Minimal QA and regression/release gate from the first commit. Review status remains `REVIEW`.
- Structured planner/tool and Skill-registry interfaces; the foundation may use deterministic explicit tool input. Natural-language LLM integration is Stage 2 and MUST NOT be represented as already implemented.

Exit: all Stage 1 automated and live acceptance rows pass on the pinned Windows Rhino/runtime. Without that environment, record `BLOCKED` or `NOT_RUN`, and deliver an implementation candidate only.

## 34.2 Stage 2 — Cladding scenario and engineering outputs

Outcome: supported canopy/cladding scenario from selected Rhino source through accepted Skill result and consistent review outputs.

Required:
- LLM gateway, bounded planner, contextual tool calling, discoverable Skill adapter and explicit capability manifest.
- Integrate existing independent `cladding-delivery` package without merging it with `cad-fabrication-engineering-v3`, renaming their identities, or forcing a new runtime dependency on either existing package.
- Deepen geometry/tools only when a golden engineering scenario requires them.
- Model, drawings, BOM and nesting outputs bound to one immutable snapshot hash and rule/Skill versions.
- Explicit unsupported-feature list; complex returns, corner/notch/cutout/join/fold allowances and other absent semantics block production and are never silently omitted.
- Review evidence and production release decision separated. Source-only cladding remains `REVIEW`; Rhino adoption alone does not change it.

Exit: golden scenario regression plus source-geometry/model/drawing/BOM consistency and human engineering release checks. Chinese labels require visual verification in final rendering; otherwise collision-safe ASCII English/pinyin labels plus reversible ID mapping.

---

# 35. Stage 3 — Expert and Design Exploration

Only after dependable Stage 1/2 gates:
- isolated expert Code Mode, explicit approvals, no unrestricted Rhino-process execution;
- Vision paired with deterministic measurement;
- branches, compare and milestone UI;
- Grasshopper integration;
- deeper model-QA/drawing-generation/quantity-takeoff Skills;
- richer evaluation and tool breadth.

Minimal model QA and regression are already mandatory in Stage 1, not deferred here.

---

# 36. Stage 4 — Team and Remote Platform

Remote Linux Agent Host, team projects, shared history, role-based approvals, remote artifact/Skill registry, multi-Agent execution, centralized policy/evaluation. Remote authentication and persistent permissions require separate design and approval. Rhino executor remains Windows-first. Linux Rhino.Compute is optional official WIP/nonproduction exploration only, not a V1 prerequisite, production claim or licensing dependency.

---

# 37. Acceptance Matrix

Each result SHALL record environment, exact source/package/runtime versions, evidence location and `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`. Fake-adapter tests never count as live Rhino acceptance.

| ID | Stage | Required evidence |
|---|---|---|
| F-01 | 1 | Actual host and RhinoCommon/Eto plugin compile with pinned dependencies; no placeholder Rhino SDK |
| F-02 | 1 | Live selected document units, tolerance, selection and identity snapshot; no context mutation |
| F-03 | 1 | Live detached Preview; Reject and pre-apply cancellation leave document unchanged |
| F-04 | 1 | Accepted Preview creates exactly expected geometry and one semantic commit/owned Undo record |
| F-05 | 1 | Live native Undo then Redo reconciles geometry, identity, revision and preview invalidation |
| F-06 | 1 | Save, close and reopen restores IDs/history references while creating a new session; old requests fail |
| F-07 | 1 | Checkpoint restore previews scope, safeguards later edits, verifies actual resulting managed model |
| F-08 | 1 | Concurrent apply, stale revision, switched/closed document, modified/deleted object and duplicate business IDs fail closed |
| F-09 | 1 | Operation retry after lost ACK produces no second mutation; changed payload under same ID is rejected |
| F-10 | 1 | BeginUndoRecord returning 0, partial mutation, disk failure and crash during apply lead to documented recovery state; never a false success |
| F-11 | 1 | Manual copy/replace/delete and undo/redo reconcile IDs; ambiguous split/join lineage is blocked |
| F-12 | 1 | Automated race/cancel/partial-failure/replay/persist/restore regression and QA/release gate run |
| S-01 | 2 | Existing Skill independence and unsupported-feature disclosure verified |
| S-02 | 2 | Cladding task through Host, Rhino Preview/Commit and consistent model/drawing/BOM snapshot |
| S-03 | 2 | Chinese glyph visual inspection or ASCII/pinyin + collision-safe ID map; no garbled delivery |
| S-04 | 2 | Production approval remains separately gated; golden fixtures and actual effects validated |

---

# 38. Initial End-to-End Showcase

The Stage 2 showcase SHOULD use the canopy/cladding scenario because it exercises both generic Harness and professional Skill behavior. Stage 1 first proves the smaller executable safety loop. Alternate-branch comparison in this narrative is Stage 3, not required to close Stage 1.

Example:

### User

> Build an aluminum cladding scheme for this canopy.

### Agent

```text
Current selection:
Canopy structure
Approx. 29.7m × 4.13m

Selected Skill:
cladding-delivery

Plan:
1. Analyze structure
2. Build cladding reference envelope
3. Panelize
4. Number panels
5. Unfold
6. BOM
7. Order data
```

Agent runs analysis and produces Preview:

```text
+84 panels
~6 reference objects
-0 objects

Status: REVIEW
```

User:

> Try max panel width 1200 instead.

System creates alternate working change and comparison.

User:

> Keep the 1500 version.

System creates semantic Commit:

```text
C018
Adopt 1500 mm panelization scheme
```

User later:

> Restore the model to the field survey milestone.

System restores the selected checkpoint with full traceability.

This showcase SHALL prove:

- Agent;
- Tools;
- Skill;
- Preview;
- ChangeSet;
- Commit;
- comparison foundation;
- Restore;
- engineering identity.

---

# 39. Architectural Decisions to Hold Unless Strong Evidence Changes Them

1. **Plugin and Agent Host remain separate.**
2. **Tool and Skill remain separate.**
3. **LLM is not the geometric source of truth.**
4. **Code Mode is not the default execution path.**
5. **ChangeSet / Commit / Restore exist from V1.**
6. **Agent tasks commit semantically, not one Rhino API call per Commit.**
7. **Engineering Entity ID is independent of Rhino GUID.**
8. **Domain logic stays in Skills, not generic Harness Tools.**
9. **V1 is local-first.**
10. **Version history is an engineering workflow feature, not only an Undo implementation.**

---

# 40. Implementation Order

1. Update this actual source-controlled spec and protocol, then begin implementation without another planning approval.
2. Build Stage 1 Host, Contracts and real Rhino adapter in parallel against shared DTOs; add failure tests with the implementation.
3. Run Linux headless tests and actual plugin compilation; separately run Windows/Rhino live acceptance when available.
4. Review findings, repair recoverable code defects, re-run affected checks; keep remaining live gates blocked if Rhino is unavailable.
5. Add the Stage 2 Skill scenario only after the Stage 1 execution/recovery foundation is accepted.
6. Expand Stage 3 and 4 only after corresponding gates.

No repository publication, installer execution on the user's computer, remote access grant or production release is implied by local implementation authorization.

---

# 41. Resolved Review Decisions and Remaining Gates

Accepted: Plugin/Host and Tool/Skill separation; local-first; task-level Commit; checkpoint plus object deltas; stable business IDs; structured tools by default; small vertical slice first; minimal QA/regression/release gate in V1.

Stage 1 uses explicit Preview acceptance for writes. It has no unrestricted script executor and no external LLM credential requirement. Broader Revert/merge, complete tool catalog and production cladding readiness remain gated, not promised by compilation.

---

# 42. Normative Execution and IPC Contract

- Every live Rhino read/duplicate/resolve/write is dispatched to the UI thread; background geometry work uses detached owned values. No live RhinoObject/RhinoDoc crosses asynchronous calculation boundaries.
- Apply is serialized per document. Check expected document ID, fresh session ID, revision, units/tolerance and object ID/fingerprint immediately before opening Undo. Validate again after any preparatory asynchronous boundary.
- Requests carry protocol version, task ID, operation ID, expected context, tool ID, typed arguments and deterministic request hash. Unknown protocol/tool/fields or invalid numbers fail closed.
- Operation IDs are idempotency keys scoped to document/task. Same ID + same hash returns the stored outcome; same ID + different payload is rejected. Restart with ambiguous apply state blocks automatic replay until recovery is reconciled.
- Local Host binds loopback only; plugin starts/uses its paired Host with a per-process nonce delivered in private process transport, never persisted or logged. No external listen address, browser-origin requests, arbitrary export path or arbitrary-code endpoint.
- Network/LLM work and user approval happen outside an Undo record. Cancellation before mutation guarantees no document changes. Once synchronous apply begins, cancellation cannot interrupt it mid-record: return its verified outcome or recovery requirement.

# 43. Normative Transaction and Recovery Contract

Rhino Undo is an interactive history facility, not ACID, a filesystem transaction or a durable rollback guarantee.

- Separate task states from operation states. Operations use `prepared → applying → committed`, with `cancelled`, `rejected`, and `failed-recovery` as explicit terminal/recovery conditions.
- Before mutation, durably save the approved request, detached before-images and checkpoint reference. Atomically replace journal files with write-through/flush; record failures honestly. No append-only claim without an actual append log.
- BeginUndoRecord returning 0 aborts before mutation. Never end an Undo record not owned by this executor; native command context and modeless UI context are distinct.
- Apply, post-effect QA, before-image compensation and closing the owned Undo record are synchronous UI-thread work. Unexpected partial effects enter `failed-recovery` unless compensation is verified. No blind Undo that could remove a human operation.
- Persist the verified outcome before acknowledging. If durable completion fails after model mutation, record/quarantine ambiguity and do not label the operation cancelled or silently retry.
- Checkpoints and managed geometry deltas are recovery artifacts; saving the model remains explicit. Preview invalidates on any context divergence. Existing original DWG/3DM inputs are never overwritten implicitly.
- Export is separately staged, checksummed and logged; only approved atomic promotion publishes it. A model Undo does not undo an external file write.
- Revert applies only no-conflict task-local inverses in V1. Restore presents scope and impact on later human edits, takes a pre-restore safeguard, preserves audit history and verifies the resulting model.

# 44. Normative Engineering Identity Lifecycle

- `EngineeringEntityId` is a stable business identity. Rhino GUID is an instance lookup only. Persist ID and lineage in supported object attributes/document metadata, and verify save/reopen.
- Replacing one logical object preserves its business ID and records old/new Rhino GUID association. Reconcile replace-event sequences at a stable UI boundary, not from a transient delete callback alone.
- Copy creates a new identity with `copiedFrom`; copied user strings MUST be detected. An unapproved manual collision is a blocking QA issue until explicitly reconciled; never silently collapse two objects.
- Split/join/boolean record many-to-many parent/child lineage and retire source identities only after successful apply. Stage 1 does not support these operators; unsupported lineage is surfaced rather than guessed.
- Human mutations, imports, native Undo/Redo, deletes and reopened files are reindexed from the actual document. Avoid mutation inside notification callbacks. Undo/Redo can resurrect or remove objects; IDs must be reconciled without automatically reapplying a task.
- Identity mapping, per-object fingerprints, actor and task provenance survive checkpoint restore; uncertain mappings block release.

# 45. Normative Model QA and Engineering Release

- Preflight: supported units, finite positive tolerance, finite dimensions/transforms, valid geometry, allowed object count/scope, unique IDs and required features present.
- Postflight: verify actual object count, actual geometry validity/dimensions and ID mapping; compare effects against the approved plan. A successful API return is insufficient.
- One snapshot hash binds all artifacts required by the current stage/tool. In Stage 2 this includes model, drawings, BOM, nesting and metadata; Stage 1 has no implied drawing/BOM/nesting deliverable. Reject mixed revisions or missing expected outputs.
- `REVIEW`, `APPROVED_FOR_PRODUCTION`, and `REJECTED/BLOCKED` are distinct. No automatic transition to production just because tests or Rhino APIs pass.
- Chinese file/drawing labels require inspection of rendered pixels in final artifact and target font environment. Without this evidence use ASCII English/pinyin names plus collision-safe identity mapping. A font installed on another machine is not visual evidence.
- Current cladding source-only limitations remain explicit. Unsupported folds/returns/cutouts/complex joints or other features block fabrication/order status.

# 46. Verification Evidence and Source References

Build/test reports SHALL include source hashes, pinned dependencies, command/exit code, test counts, failure injection coverage and separate live acceptance status. A release gate fails while a required live row is `BLOCKED` or `NOT_RUN`. README capability claims must match this matrix.

Primary API references (checked 2026-10-08):
- Rhino .NET runtime baseline: https://www.rhino3d.com/en/docs/guides/netcore/ (Rhino 8.20 defaults to .NET 8; later releases still require explicit qualification).
- Undo API: https://developer.rhino3d.com/api/rhinocommon/rhino.rhinodoc/beginundorecord
- Undo semantics: https://docs.mcneel.com/rhino/8/help/en-us/commands/undo.htm
- Threaded document reads discussion: https://discourse.mcneel.com/t/async-multithreaded-document-read/201922
- Persisted plugin/object metadata: https://developer.rhino3d.com/guides/rhinocommon/plugin-user-data/
- Detached display preview: https://developer.rhino3d.com/en/guides/rhinocommon/display-conduits/

This v0.2 is an amendment of the actual v0.1 repository spec, not a reconstructed replacement. Original sections 1–33 and 38–39 retain product architecture; sections 34–37 and 40–46 now define implementable stages and mandatory safety contracts.
