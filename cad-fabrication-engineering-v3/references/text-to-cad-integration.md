# text-to-cad / cadgen integration

Use the installed text-to-cad/cadgen skill files as the runtime source of truth. At the time this package was reviewed, upstream `latest` used a cadgen 0.7.x release line; do not hard-code an old interface if the installed skill has migrated.

When cadgen/build123d is available, it is the preferred CAD/documentation runtime:

- map one maintained Geometry IR configuration to one parameterless build123d model entrypoint;
- emit STEP as the saved geometry artifact;
- measure and validate geometry from the model, not from screenshots;
- project engineering views from the part/assembly geometry, including hidden lines where useful;
- import shared model facts into drawing code rather than retyping dimension values;
- use standard drawing scales, title blocks and overlap diagnostics;
- create DXF cut/flat geometry from actual planar model geometry;
- generate and review at least one snapshot after visible STEP geometry changes;
- edit source/IR and regenerate rather than patching final STEP/DXF/PDF bytes.

## Compatibility backend

The included CadQuery/OCP path implements the same conceptual contract:

- CadQuery/OCP builds the B-Rep/STEP;
- OCCT HLR projects visible/hidden engineering view linework from that B-Rep;
- ReportLab lays controlled A3 document sheets around those projected views;
- ezdxf writes 1:1 engineering projection DXF with semantic layers;
- the runner re-opens STEP/PDF/DXF for QA.

This makes drawing quality independent of whether cadgen happens to be available on a particular workstation.

## Important limit

The preferred cadgen engineering-drawing layer currently focuses on orthographic/document views and does not replace domain-specific façade sections, node details or sheet-metal unfolding logic. Those remain explicit project/domain responsibilities in this skill.
