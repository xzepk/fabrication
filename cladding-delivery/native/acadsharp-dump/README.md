# ACadSharp DWG helper

Cross-platform .NET 8 command-line helper used by the Python Skill so DWG parsing stays isolated behind a stable JSON contract.

```bash
dotnet publish ACadSharpDump.csproj -c Release --artifacts-path /absolute/external-runtime/build -o /absolute/external-runtime/acadsharp
```

Then point `CADFAB_ACADSHARP_DUMP` to the generated executable or `dotnet .../ACadSharpDump.dll` command.

For paths containing spaces, backslashes or non-ASCII characters, prefer the
unambiguous argument-array setting (also works on Linux):

```powershell
$env:CADFAB_ACADSHARP_DUMP_ARGV = '["C:\\Program Files\\dotnet\\dotnet.exe","C:\\cad-runtime\\ACadSharpDump.dll"]'
```

`CADFAB_ACADSHARP_DUMP_ARGV` takes precedence over the legacy command string.

The helper intentionally performs inspection only. Project-specific entity normalization should be added here or in a separate adapter while preserving entity handles, block/XRef transform paths and reader notifications.

## 3.1 inspection acceptance

The helper emits UTF-8 JSON, the original DWG SHA-256, ACadSharp assembly version,
`canonical_level: INSPECTION_ONLY` and `production_geometry_ready: false`.
Entity counts refer to model space; they are not total expanded block-instance
counts. Reader notifications remain intact, including unknown object and missing
dynamic-block references. Do not discard these or promote inventory to verified
engineering geometry.

Keep the .NET SDK, NuGet cache, build intermediates and published binaries outside
the skill. The package contains adapter source only. The `--artifacts-path` option
requires .NET 8+: https://learn.microsoft.com/dotnet/core/sdk/artifacts-output.

From the skill root, after configuring `CADFAB_ACADSHARP_DUMP`, run:

```bash
python scripts/validate_dwg_runtime.py --input /path/to/original-dwgs --out /path/to/fresh-inspection-report
```

The input may instead be one `.dwg` file. Source files are read only and their hashes
must remain unchanged. The output folder must be new. Windows supports the same
commands with absolute Windows paths, but the 3.1 review build was tested on Linux
only; Windows native execution remains unverified.
