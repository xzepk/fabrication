# Cladding REVIEW adapter

This adapter calls the existing independent `cladding-delivery` 3.1.0 OCCT provider,
identity, BOM and shelf-nesting library functions. It never invokes or simulates the
skill CLI's human-confirmation gates. Neither independent skill is changed, merged,
installed into the other, or made dependent on this adapter.

## Runtime

The verified Linux x64 runtime is Python 3.12 with CadQuery 2.8.0, cadquery-ocp
7.9.3.1.1, cadquery-ocp-proxy 7.9.3.1.1 and ezdxf 1.4.4. Direct CAD requirements are
pinned in `runtime-requirements.txt`; this is not a complete transitive lockfile.
Python must also satisfy the independent skill's Python >=3.11,<3.15 requirement.
Actual runtime versions are recorded in every `provenance.json`.

When an external virtual environment has been authorized, its interpreter can
install the pinned dependencies from the official PyPI registry:

```text
<external-venv-python> -m pip install -r adapters/cladding/runtime-requirements.txt
```

No installation is performed by the adapter. The original independent skill
sources remain at their trusted absolute path. Windows wheels, Rhino execution,
UI adoption/Undo and production engineering qualification need separate real
Windows/Rhino acceptance; these Python results do not qualify them.

## Invocation

Only the trusted C# Host supplies paths and the validated envelope. It runs the
adapter with isolated imports, bytecode writes disabled and a new cache prefix:

```text
<python> -I -B -X pycache_prefix=<new-stage>/python-cache <adapter>/run.py --skill-root <absolute-independent-skill> --request <absolute-envelope.json> --output <absolute-new-output>
```

The output path must not exist, its parent must exist, and original input/skill
paths cannot be output destinations. Request JSON cannot choose paths, import
names, providers, code or executables. The adapter invokes no subprocess or
network operation. There is no arbitrary-code endpoint; this is not a general
sandbox for untrusted Python or hostile installed native dependencies.

The envelope binds request, snapshot, job, skill sources and exact adapter rules.
`skillSourceHash` is SHA-256 of the independent skill's `MANIFEST.sha256` bytes;
each listed source is verified, and unlisted source files or links are rejected.
The rule suffix is uppercase SHA-256 over these sorted ASCII lines:

```text
capabilities.json <UPPERCASE SHA256>\n
request.schema.json <UPPERCASE SHA256>\n
run.py <UPPERCASE SHA256>\n
```

The prefix is `rhino-cladding-planar-v1:`. The trusted Host owns the C# JSON request
hash calculation and validates the actual Rhino snapshot/selection. Python
cross-binds the supplied commitments, repeats strict JSON/numeric/geometry checks,
and preserves the complete envelope without inventing an original drawing hash.

## Outputs and acceptance

Supported solids are individual axis-aligned plain rectangular plates in XY, XZ
or YZ. Quantity must be 1; all dimensions, material and density are explicit.
Selected-source dimensions refer to the original design values; optional measured,
used and adoption-basis records remain distinct. Origin is the minimum world XYZ
corner. Unsupported holes, folds, returns, tubes, slots or unknown fields fail
before geometry creation rather than silently becoming a rectangle.

The provider first creates and reads back a local STEP. This adapter rotates and
translates that actual shape, exports the world STEP, independently reimports it,
and checks BRep validity, one closed solid, six planar faces, interior, bounds,
positive volume and surface area. Bounds use 1e-5 mm absolute tolerance and mass
uses 1e-7 relative tolerance. These are numerical serialization checks, not
fabrication, installation or survey tolerances.

Each component has `model/<machine>.step`, `blank/<machine>_flat.dxf`, a reversible
identity JSON, and plate-local orthographic review DXF/SVG. `assembly-review.svg`
projects the same exact world preview boxes, with a numbered collision-safe ASCII
ID legend and snapshot hash. SVG text is ASCII; original Unicode labels are
preserved in UTF-8 JSON/BOM. Chinese-glyph visual qualification is not claimed.

Shared files are the immutable input envelope, provenance, label map, BOM JSON/CSV,
nesting, assembly SVG, readback and manifest. BOM mass uses actual STEP readback.
CSV prefixes potentially executable formulas; exact original strings stay in
JSON. Stock is never invented: null gives `NOT_CONFIGURED`, supplied unconfirmed
process gives `REVIEW` with `PROCESS_UNCONFIRMED` and no placements, and oversized
unplaced blanks give `BLOCKED`. Confirmed stock uses review-only unrotated shelf
nesting, separated by material, grade and thickness.

`verify_output(root, envelope)` checks exact paths/files, bounds (1000 files,
32 MiB/file, 128 MiB total), no symlinks/reparse points/hardlinks, hashes, revision
bindings, real STEP/DXF readback, identity/BOM/nesting consistency and deterministic
per-part/assembly SVG bytes. The Host independently pins the manifest hash and
revalidates before adoption. Hashes are integrity evidence, not a digital signature
or protection against an attacker replacing every trusted input and source.

No successful manifest is retained after failed final acceptance. Partial output
is evidence, cannot be reused/overwritten, and must not be adopted. All successful
outputs stay `REVIEW`, `manufacturingRelease=false`, `releaseDecision=NOT_RELEASED`;
no scope/survey confirmation, production release, CAM or CNC qualification is
invented. Native geometry success alone does not establish engineering validity.

## Real regression tests

From the `rhino-ai-assistant` module root, with the real CAD runtime installed:

```text
<python> -B -m unittest discover -s adapters/cladding -p "test_*.py" -v
```

The tests use real OCCT STEP export/import and ezdxf readback, all three orientations,
translated origins, measurements, Chinese-label identity maps, missing stock,
strict unsupported-input rejection, hash-recomputed corrupt geometry, symlink and
partial-output failures, bounded SVG layouts, and the 56-part nominal-skin canopy
fixture. They do not use fake geometry and do not claim live Rhino acceptance.
