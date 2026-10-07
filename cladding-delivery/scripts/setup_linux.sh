#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$PYTHON_BIN" -m venv "$ROOT/.venv"
source "$ROOT/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -e "$ROOT"
echo "Python environment ready: $ROOT/.venv"
if command -v dotnet >/dev/null 2>&1; then
  echo "dotnet found: $(dotnet --version)"
  echo "Build DWG helper with: dotnet publish $ROOT/native/acadsharp-dump/ACadSharpDump.csproj -c Release"
else
  echo "dotnet not found. This is OK for DXF-only use; install .NET 8 SDK for direct DWG parsing."
fi
