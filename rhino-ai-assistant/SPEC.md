# Rhino AI Agent Harness — Product & Technical Specification

> Status: Draft for Review  
> Version: 0.1  
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
- .NET compatible with Rhino 8
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

V1 target: approximately 30–50 high-confidence Tools, not hundreds of low-level wrappers.

---

# 11. Rhino Execution Model

## 11.1 UI-thread execution

Agent/HTTP work MAY run asynchronously.

Any Rhino document mutation SHOULD be dispatched through the Rhino UI execution path before mutating `RhinoDoc`.

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

Policy: may auto-execute inside one Undo transaction, followed by ChangeSet/Commit.

## R2 — Structural Change

Examples:

- repanelization;
- mass replacement;
- large-scale deletion;
- major geometry rebuild.

Policy: Preview required before applying unless user has explicitly trusted the operation.

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

R2 changes SHOULD support an interactive model preview.

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

Create a new Commit that inverses an older Commit.

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

Restore SHOULD be explicit and SHOULD create a traceable event/commit instead of silently deleting history.

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

Branching is Phase 2 unless implementation cost is low enough to include in V1.

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

V1 SHOULD include an evaluation harness instead of evaluating only by visual impression.

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

# 34. MVP Scope

V1 MUST prove the complete Harness architecture, not feature breadth.

## 34.1 UI

Required:

- Floating Assistant;
- Dock Panel;
- Chat;
- Task Timeline;
- Changes Timeline.

## 34.2 Context

Required:

- active document;
- units/tolerance;
- layers;
- selection;
- basic geometry summary;
- viewport capture.

## 34.3 Tools

Required:

- approximately 30 core read/edit geometry/object/layer/document Tools;
- schema validation;
- risk levels;
- Undo support.

## 34.4 Agent Runtime

Required:

- LLM Gateway abstraction;
- Tool Calling;
- simple task planner;
- persistent task state;
- policy enforcement.

## 34.5 Versioning

Required in V1:

- Rhino Undo transaction;
- ChangeSet;
- Commit;
- Change Timeline;
- Revert;
- Restore;
- persistent Engineering Entity ID;
- checkpoint + delta architecture.

## 34.6 Preview

Required for R2:

- object-level add/modify/delete preview;
- Apply / Reject;
- ChangeSet summary.

## 34.7 Skill integration

Required:

- Skill Registry;
- invoke `cladding-delivery`;
- receive structured progress/results;
- map generated engineering objects into Rhino;
- preserve engineering IDs;
- create Commit after acceptance.

---

# 35. Phase 2

After V1:

- design branches;
- branch comparison;
- Milestone UI;
- Vision Agent;
- richer Code Mode;
- Grasshopper integration;
- model-qa Skill;
- drawing-generation Skill;
- quantity-takeoff Skill;
- more sophisticated evaluation.

---

# 36. Phase 3

Enterprise/platform stage:

- remote Linux Agent Platform;
- team projects;
- shared version history;
- role-based approval;
- remote Artifact Store;
- organization Skill registry;
- multi-Agent execution;
- enterprise LLM routing;
- centralized evaluation;
- project policy management.

---

# 37. V1 Acceptance Criteria

V1 is successful only if the following end-to-end flows are demonstrably working.

## AC-01 Read context

User can ask:

> What are the currently selected objects?

Agent returns accurate Rhino-derived information without mutation.

## AC-02 Reversible edit

User requests:

> Move these objects to a new layer.

System:

1. creates/uses structured Tool Calls;
2. executes in Rhino;
3. creates one Undo transaction;
4. generates ChangeSet;
5. creates Commit;
6. Ctrl+Z or Agent Undo correctly reverses it.

## AC-03 Preview

User requests a large model change.

System shows add/modify/delete Preview before commit and does not mutate authoritative state until Apply.

## AC-04 Revert

Given C001 → C002 → C003, user can revert C002 while preserving history, producing a new Commit.

## AC-05 Restore

User can restore a previous checkpoint/Commit and the resulting Rhino geometry and engineering entity mapping are consistent.

## AC-06 Human edit tracking

A relevant manual Rhino edit is detected and appears in the Working Model / Change tracking layer.

## AC-07 Persistent engineering ID

Replacing/rebuilding a Rhino object does not lose its EngineeringEntityId when the operation represents the same engineering object.

## AC-08 Skill integration

User requests a supported cladding task.

Agent invokes `cladding-delivery`, displays plan/progress, produces structured engineering outputs, creates Rhino objects with engineering IDs, and records accepted changes in version history.

## AC-09 Risk policy

R0 executes automatically; R2 requires Preview; R3 requires explicit confirmation.

## AC-10 Failure transparency

Unsupported geometry or Skill cases are surfaced as explicit blocked/unsupported results and are never silently approximated into production-ready geometry.

---

# 38. Initial End-to-End Showcase

The first showcase SHOULD use the canopy/cladding scenario because it exercises both generic Harness and professional Skill behavior.

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

# 40. Recommended Implementation Order

```text
1. Rhino Plugin shell
      ↓
2. Agent Host + protocol
      ↓
3. Context Collector
      ↓
4. Core Tool Registry + Executor
      ↓
5. Undo transaction
      ↓
6. Change Tracker
      ↓
7. ChangeSet / Commit / Restore
      ↓
8. Preview
      ↓
9. Skill Registry
      ↓
10. cladding-delivery integration
      ↓
11. End-to-End canopy showcase
      ↓
12. Branch / Vision / Code / Grasshopper expansion
```

Do not prioritize pet animation, broad LLM provider support, or hundreds of Rhino commands before the execution/version architecture is validated.

---

# 41. Review Questions

The first architecture review SHOULD focus on:

1. Is Plugin / Agent Host separation accepted?
2. Is Tool / Skill separation accepted?
3. Is ChangeSet / Commit / Restore mandatory for V1?
4. Should R1 reversible Agent edits auto-commit or remain uncommitted until user approval?
5. What is the preferred storage for geometry deltas and full 3DM checkpoints?
6. Does V1 need Branch, or can Branch remain Phase 2 while the DAG-compatible data model is implemented now?
7. How should `cladding-delivery` exchange geometry with Rhino: canonical geometry contract, file artifacts, or both?
8. Which 30–50 Rhino Tools constitute the minimum viable Tool Registry?
9. Which operations are R2 versus R3 for the first engineering deployment?
10. What level of human edit tracking is required before the first production pilot?
