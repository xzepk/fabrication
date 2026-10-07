#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Runtime and native builds never live inside the reusable skill package.
VENV="${CLADDING_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/cladding-delivery/venv}"
ROOT_REAL="$("$PYTHON_BIN" -c 'import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve())' "$ROOT")"
VENV_REAL="$("$PYTHON_BIN" -c 'import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve())' "$VENV")"
case "$VENV_REAL/" in "$ROOT_REAL/"*) echo "Refusing runtime inside skill: $VENV_REAL" >&2; exit 2;; esac
if [[ ! -f "$VENV_REAL/pyvenv.cfg" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_REAL"
fi
PY="$VENV_REAL/bin/python"
"$PY" -m pip install -U pip
# setuptools can create build/egg-info in its source tree, even without -e.
# Build from an external disposable copy so the reusable skill stays byte-clean.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$ROOT" "$STAGE/cladding-delivery"
"$PY" -m pip install "$STAGE/cladding-delivery${CLADDING_EXTRAS:+[$CLADDING_EXTRAS]}"
echo "External Python runtime: $VENV_REAL"
echo "Optional provider: CLADDING_EXTRAS=build123d (or build123d,test). ODA is never required."
echo "For DWG, build ACadSharp into an EXTERNAL work directory; see references/operations.md."
