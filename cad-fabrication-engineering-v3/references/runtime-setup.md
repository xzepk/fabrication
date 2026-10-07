# External runtime setup and acceptance

This is setup guidance for an authorized environment, not an auto-installer. Nothing below vendors runtime packages into the skill or installs another skill. The two fabrication skills remain independent.

## Compatibility and drawing environment

Use Python 3.11+ in a virtual environment outside this directory. Install the skill's `requirements.txt` from PyPI using that environment's Python. The reference review used Python 3.12.14, CadQuery 2.7.0, OCP 7.8.1.1.post1, build123d 0.10.0, ezdxf 1.4.4 and ReportLab 4.4.9. Record your resolved versions with `python -m pip freeze` and do not assume another combination has passed.

```sh
python -m venv /path/to/cadfab-compat
/path/to/cadfab-compat/bin/python -m pip install -r /path/to/skill/requirements.txt
```

On Windows use the virtual environment's `Scripts/python.exe` rather than `bin/python`. Configured interpreter paths are single executable paths, not shell commands with flags.

## Separate cadgen environment

The current public provider uses the official MIT `earthtojake/text-to-cad` runtime from PyPI. Install it outside the skill:

```sh
python -m venv /path/to/cadgen-runtime
/path/to/cadgen-runtime/bin/python -m pip install 'cadgen==0.7.15'
/path/to/cadgen-runtime/bin/python -m pip check
/path/to/cadgen-runtime/bin/python -m pip freeze > /path/to/cadgen-runtime-resolved.txt
```

The resolver currently selects build123d 0.11.1 and cadquery-ocp-novtk 7.9.3.1.1. Retain the freeze file with deployment records; it is an environment lock record, not portable binaries. Do not upgrade the skill's CadQuery/OCP environment to satisfy cadgen indirectly.

The cadgen public model pipeline needs local IPC sockets and temporary workers even with `CADGEN_DAEMON=0`. Use an environment where that normal runtime behavior is permitted. Do not patch out safety checks, fake a broker, weaken system security settings or bypass an environment denial. A kernel probe alone is insufficient export acceptance. The adapter disables update checks and usage analytics for its worker and puts temporary caches outside the delivery.

## Project selection and fresh outputs

```sh
python scripts/run_project.py config/canopy-reference-validation.yaml /path/to/run-cq --backend cadquery
python scripts/run_project.py config/canopy-reference-validation.yaml /path/to/run-build123d --backend build123d
python scripts/run_project.py config/canopy-reference-validation.yaml /path/to/run-cadgen --backend cadgen --runtime-python /path/to/cadgen-runtime/bin/python
```

Each output directory must be new. Previous runs and user inputs are never removed. To allow selection based on runtime availability, request `--backend auto` explicitly; any error after provider selection is fatal and does not fall back.

Equivalent optional YAML:

```yaml
cad_runtime:
  backend: cadgen
  python: /path/to/cadgen-runtime/bin/python
  requirements: [nominal_rectangular_panels, orthographic_views, reference_layout]
```

The above requirements are the complete verified capability vocabulary. Requests such as `sections`, `true_flat_patterns`, `curved_panels`, or `production_release` are deliberately refused. Runtime selection cannot upgrade nominal reference geometry into a fabrication model.

## Acceptance commands

Install pytest in the test environment if needed, then run:

```sh
PYTHONDONTWRITEBYTECODE=1 CADFAB_TEST_CADGEN_PYTHON=/path/to/cadgen-runtime/bin/python python -m pytest -p no:cacheprovider -v tests/test_runtime_backends.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python scripts/golden_regression.py --output /path/to/run-cq
python scripts/validate_skill.py .
```

Without `CADFAB_TEST_CADGEN_PYTHON`, the optional current-cadgen/current-build123d external tests are skipped and must not be reported as passing. A managed-environment socket denial is also an explicit cadgen export skip/blocker. The test suite exercises actual CadQuery and build123d exports, immutable inputs, readback geometry and failure policy; mocks are limited to fallback/error-policy tests. Inspect PDF previews after source or geometry changes and retain the manifest, QA JSON and test report with the run.

## Text/font environment and portable labels

`CADFAB_CJK_FONT` is an exclusive approved-font override. When set, the font checker does not silently search another font if that file is missing or lacks required glyphs; this makes missing-font acceptance tests repeatable. Font files are environment dependencies and are never bundled in the skill. Without that override, the label policy searches the system font inventory and verifies coverage and actual PDF embedding/readback.

Optional `display_labels` in the project YAML maps exact original text to reviewed ASCII English/pinyin labels; the runner copies that mapping into the IR. Keep safety notes complete and review the translation. Unknown/untranslated safety notes fail QA rather than disappearing. ASCII ID display values and project filenames use deterministic portable mappings while original project/part IDs remain in IR, manifests and BOM alongside `display_id`. Label mappings are delivered as sidecar JSON and checked against the rendered PDF/DXF. Never rename source drawings to make display text convenient.
