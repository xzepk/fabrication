# Architecture - v3.4 local review build

```text
DWG / DXF / PDF / field data
          |
          v
External parser adapters (ACadSharp primary / ODA optional fallback / explicit DXF debug)
          |
          | raw evidence: handles, layers, blocks/XRefs, transforms, dimensions, warnings
          v
Normalizer + semantic resolver
          |
          v
Geometry IR 1.1  <---- Human Gate A / confirmed rules
          |
          +----------------------+-----------------------+
          |                      |                       |
          v                      v                       v
Parametric B-Rep             Documentation          Quantities
cadgen/build123d/OCP         Saved STEP -> OCCT HLR   BOM / type schedule
CadQuery/OCP default         engineering drawing     release-state metrics
Project-specific adapters            |
          |                        +--> PDF (controlled document)
          +--> STEP               +--> engineering DXF (1:1 model-space projection)
          |
          +--> fabrication solid (only after folds/nodes confirmed)
                    |
                    +--> true flat pattern DXF
                    +--> nesting / purchase quantity

Human Gate B / survey -> invalidate impacted IR -> regenerate all downstream artifacts

QA: geometry + dimensional closure + PDF coverage + DXF audit + cross-artifact counts + golden regression
```

The important boundary is between **evidence/semantics** and **geometry generation**. The parser does not decide fabrication rules; the LLM does not own final numeric geometry; drawings do not become a second source of truth.

The current executable adapter implements nominal rectangular panels only. Fabrication solid, true unfolding, sections, freeform routes and production release shown as extension goals above are not provided by this runner. External-provider and runtime acceptance details: [integration contract](text-to-cad-integration.md).
