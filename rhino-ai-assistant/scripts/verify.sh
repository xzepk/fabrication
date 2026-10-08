#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DOTNET="${DOTNET:-dotnet}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export MSBuildEnableWorkloadResolver=false
mkdir -p evidence
"$DOTNET" --info > evidence/dotnet-info.txt
"$DOTNET" restore RhinoAi.sln --locked-mode -m:1 | tee evidence/restore.log
"$DOTNET" build RhinoAi.sln --no-restore -c Release -m:1 | tee evidence/build.log
"$DOTNET" tests/RhinoAi.Core.Tests/bin/Release/net8.0/RhinoAi.Core.Tests.dll | tee evidence/core-tests.log
"$DOTNET" tests/RhinoAi.Host.IntegrationTests/bin/Release/net8.0/RhinoAi.Host.IntegrationTests.dll | tee evidence/host-tests.log
python3 scripts/test_release_gate.py | tee evidence/release-gate-tests.log
python3 scripts/release_gate.py evidence/acceptance.json
