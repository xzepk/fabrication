# Windows / Linux operations

## External runtime only

Keep the skill directory source-only. Use Python 3.11–3.13 with compatible native wheels in an external virtual environment. Tested versions for the current local run are recorded in the validation report; dependency ranges are not a Windows certification.

Linux:

```bash
CLADDING_VENV="$HOME/.local/share/cladding-delivery/venv" CLADDING_EXTRAS=build123d,test bash <skill>/scripts/setup_linux.sh
```

Windows PowerShell (provided, not executed in Linux validation):

```powershell
& <skill>\scripts\setup_windows.ps1 -Venv "$env:LOCALAPPDATA\cladding-delivery\venv" -Extras "build123d,test"
```

Both scripts reject a runtime inside the skill, reuse an existing virtual environment, and install from an external temporary source copy to keep build metadata out of the skill. They install CadQuery, ezdxf, PyYAML and jsonschema; build123d and pytest are optional extras. `scripts/run.py` uses source directly, so invoke it with the external environment's Python. Do not copy site-packages, native DLL/SO/PYD files, license files, outputs, caches, or a virtual environment into the skill. The source `native/acadsharp-dump/` is allowed; build its outputs elsewhere.

## DWG runtime

Only direct DWG inspection needs .NET 8 SDK/runtime plus ACadSharp. DXF inspection and model-driven workflows do not. Copy the helper source to a separate build directory and publish from there:

```bash
mkdir -p <runtime>/acadsharp-src
cp <skill>/native/acadsharp-dump/ACadSharpDump.csproj <skill>/native/acadsharp-dump/Program.cs <runtime>/acadsharp-src/
dotnet publish <runtime>/acadsharp-src/ACadSharpDump.csproj -c Release -o <runtime>/acadsharp-bin
export CADFAB_ACADSHARP_DUMP=<runtime>/acadsharp-bin/ACadSharpDump
```

Windows: perform the equivalent `Copy-Item` and `dotnet publish`, then set `CADFAB_ACADSHARP_DUMP` to the external `.exe`. Keep .NET runtime/native builds out of the skill. A Windows parser/provider run, Rhino service, ODA conversion, physical samples and shop-floor CAM validation are separate acceptance stages; do not call them passed after Linux tests.

ODA is optional and never required. No automatic ODA installation or conversion fallback is provided. If a project separately authorizes a conversion, retain the original DWG, record converter/version/settings and output hashes, then inspect the resulting DXF with an explicit conversion provenance record. CAD applications and their commercial runtimes are not bundled.

## Recovery and switching providers

All projects/runs/proposals remain outside the skill. Runs have fresh IDs and refuse existing output names. Input/config changes invalidate human confirmations; obtain confirmations for the new snapshot. A provider change is explicit configuration and never an automatic error fallback.

`run` returns 2 when any geometry/unfold/nesting blocker remains while preserving its REVIEW report. `verify` returns 2 for missing/corrupt/unacceptable artifacts. Geometric verification does not release production. Packaging a run with recorded unsupported components is allowed only as an explicitly marked REVIEW issue package, never a complete manufacturing set.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<skill>/src <runtime>/venv/bin/python -m pytest -p no:cacheprovider <skill>/tests --basetemp=<external-validation>/tmp
PYTHONDONTWRITEBYTECODE=1 python <skill>/scripts/validate_skill.py <skill>
```

Use external test output directories. Refresh `MANIFEST.sha256` after source changes; it lists package files only and excludes itself.

The installed `cladding-delivery` console entry includes config/schema resources under the environment share directory. Validate both source invocation and installed console commands when changing packaging.
