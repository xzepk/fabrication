# External DWG adapter contract v1

The Skill contains no DWG runtime. ACadSharp and ODA are environment dependencies exposed through adapter commands.

## Runtime roles

- **ACadSharp**: primary parser.
- **ODA Drawings SDK**: optional fallback for unsupported/proxy/custom-object fidelity or when ACadSharp cannot complete the parse.
- The Skill does not install, license, compile, ship or update either runtime.

## Command discovery

- `CADFAB_ACADSHARP_CMD`, default `cadfab-acadsharp-dump`
- `CADFAB_ODA_CMD`, default `cadfab-oda-dump`

Each value may be a command plus fixed arguments. The Skill appends:

```text
parse --input <absolute.dwg> --output <absolute-output-directory>
```

The adapter must exit non-zero on runtime/parse failure and must write `<output>/parser-evidence.json` on success.

## `parser-evidence.json`

Minimum top-level fields:

```json
{
  "schema": "cadfab.parser-evidence.v1",
  "success": true,
  "source": {"path": "...", "sha256": "...", "dwg_generation": "AC1032"},
  "parser": {"name": "ACadSharp", "version": "..."},
  "drawing": {"units": "mm"},
  "layers": [],
  "blocks": [],
  "notifications": []
}
```

A block/entity package must preserve, where available:

- entity handle, native/DXF object type, layer and model/paper-space owner;
- block/XRef path and complete transform information for nested inserts;
- analytic line/arc/circle/ellipse/spline identity instead of tessellated approximations;
- DIMENSION measurement/text/definition points/style references;
- TEXT/MTEXT/ATTRIB content and placement/alignment;
- proxy/custom-object and unsupported-entity notifications;
- XRef resolution status, font/style warnings and units.

## Fail-closed policy

- Missing XRefs, proxy/custom entities, unsupported dimensions, unknown units or failed transforms are issues, never silent omissions.
- Exit code 0 means only that the adapter completed. Production readiness additionally requires evidence/coverage QA.
- Default parser selection is ACadSharp.
- ODA is invoked only with explicit `--parser oda` or explicit `--parser auto` fallback policy.
- `auto` attempts ACadSharp first and may attempt ODA only after ACadSharp fails to complete. It never merges entity streams.
- Every attempt, return code, adapter command identity and selected parser must be recorded in the parse manifest.
