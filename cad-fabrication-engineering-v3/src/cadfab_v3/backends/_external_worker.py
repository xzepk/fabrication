"""Tiny runtime probe. Executed by a selected Python, never imports user model code."""
from __future__ import annotations
from importlib import metadata
import importlib
import json
import sys


def probe(provider: str) -> dict:
    if provider not in {"cadquery", "build123d", "cadgen"}:
        raise ValueError("Unknown runtime provider")
    module = importlib.import_module(provider)
    if provider == "cadgen":
        # Importing a lazy package alone does not establish a working geometry kernel.
        from cadgen import step, read_step, build123d as bd
        test = bd.Box(1, 2, 3)
        if not test.is_valid:
            raise RuntimeError("Invalid build123d kernel probe")
        if metadata.version("cadgen") != "0.7.15":
            raise RuntimeError("cadgen adapter is verified only for 0.7.15; revalidate before upgrading")
    elif provider == "build123d":
        test = module.Box(1, 2, 3)
        if not test.is_valid:
            raise RuntimeError("Invalid build123d kernel probe")
        if metadata.version("build123d") not in {"0.10.0", "0.11.1"}:
            raise RuntimeError("build123d adapter is verified only for 0.10.0 and 0.11.1")
    else:
        if not module.Workplane("XY").box(1, 2, 3).val().isValid():
            raise RuntimeError("Invalid CadQuery kernel probe")
    versions = {}
    for name in ("cadgen", "build123d", "cadquery", "cadquery-ocp", "cadquery-ocp-novtk"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {"ok": True, "provider": provider, "python_version": sys.version.split()[0],
            "module_path": module.__file__, "versions": versions, "kernel_smoke_test": "1x2x3_box_valid"}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "probe":
        raise SystemExit("usage: _external_worker.py probe cadquery|build123d|cadgen")
    print(json.dumps(probe(sys.argv[2]), sort_keys=True))
