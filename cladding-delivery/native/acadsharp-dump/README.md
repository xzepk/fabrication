# ACadSharp DWG helper

Cross-platform .NET 8 command-line helper used by the Python Skill so DWG parsing stays isolated behind a stable JSON contract.

```bash
dotnet publish ACadSharpDump.csproj -c Release
```

Then point `CADFAB_ACADSHARP_DUMP` to the generated executable or `dotnet .../ACadSharpDump.dll` command.

The helper intentionally performs inspection only in v3.0.0. Project-specific entity normalization should be added here or in a separate adapter while preserving entity handles, block/XRef transform paths and reader notifications.
