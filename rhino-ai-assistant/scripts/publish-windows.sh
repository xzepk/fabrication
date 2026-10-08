#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DOTNET="${DOTNET:-dotnet}"
"$DOTNET" publish src/RhinoAi.Host/RhinoAi.Host.csproj -c Release -r win-x64 --self-contained false -p:RestoreLockedMode=true -p:NuGetLockFilePath=packages.win-x64.lock.json -o artifacts/windows-candidate/host -m:1
mkdir -p artifacts/windows-candidate/plugin
cp src/RhinoAi.Plugin/bin/Release/net8.0-windows/RhinoAi.Plugin.rhp src/RhinoAi.Plugin/bin/Release/net8.0-windows/RhinoAi.Plugin.deps.json src/RhinoAi.Plugin/bin/Release/net8.0-windows/RhinoAi.Core.dll src/RhinoAi.Plugin/bin/Release/net8.0-windows/RhinoAi.Contracts.dll artifacts/windows-candidate/plugin/
printf '\nCross-built Windows candidate only. Live Rhino acceptance remains required.\n'
