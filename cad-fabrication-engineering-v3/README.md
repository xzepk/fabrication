# CAD Fabrication Engineering Skill v3.3

V3.3 keeps the V3.2 Geometry-IR/B-Rep/drawing-quality pipeline and tightens the DWG runtime boundary.

## Parser architecture

- **ACadSharp is the primary DWG parser runtime.**
- **ODA Drawings SDK is an optional environment-level fallback.**
- Neither ACadSharp/.NET nor ODA runtime/helper code is bundled in this Skill.
- The environment exposes parser adapters through `CADFAB_ACADSHARP_CMD` and optionally `CADFAB_ODA_CMD`.
- The Skill owns invocation policy, parser-neutral evidence normalization, Geometry IR, modeling, drawings, QA and regression.
- Default selection is `acadsharp`; ODA is used only by explicit `oda` or explicit `auto` policy.
- Parser outputs are never silently merged.

This keeps licensing, runtime updates and OS-specific installation outside the Skill while preserving deterministic project behavior.

See `references/dwg-adapter-contract.md` and `SKILL.md`.
