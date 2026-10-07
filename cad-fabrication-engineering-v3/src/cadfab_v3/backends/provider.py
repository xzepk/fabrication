"""Explicit local CAD runtime selection. No runtime or third-party source is bundled."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
import copy
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile

WORKER = Path(__file__).with_name("_external_worker.py")
BACKENDS = ("cadquery", "build123d", "cadgen", "auto")
SUPPORTED_REQUIREMENTS = {"nominal_rectangular_panels", "orthographic_views", "reference_layout"}


class BackendError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, env: dict | None = None, timeout: float = 180) -> subprocess.CompletedProcess:
    """No shell, isolated import path; kill the process group on timeout on POSIX."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env, start_new_session=os.name == "posix")
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
        raise BackendError(f"CAD runtime timed out after {timeout:g}s; no fallback attempted") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def validate_capabilities(ir: dict, requirements: list[str] | None = None) -> None:
    """All implemented providers are nominal box-panel adapters, not fabrication solvers."""
    unsupported = set(requirements or ()) - SUPPORTED_REQUIREMENTS
    if unsupported:
        raise BackendError(f"Unverified engineering requirements: {', '.join(sorted(unsupported))}")
    if ir.get("units") != "mm" or ir.get("geometry_level") != "NOMINAL_SKIN":
        raise BackendError("Only millimetre NOMINAL_SKIN geometry is verified by this adapter")
    if ir.get("status") not in {"REFERENCE_VALIDATION", "PRELIMINARY", "SURVEY_PENDING"}:
        raise BackendError("This nominal adapter cannot establish production release")
    if ir.get("metrics", {}).get("flat_pattern_released"):
        raise BackendError("This adapter does not generate verified flat patterns")
    if not ir.get("parts"):
        raise BackendError("At least one nominal panel is required")
    ids = set()
    for part in ir["parts"]:
        if part.get("id") in ids:
            raise BackendError("Duplicate part identifiers")
        ids.add(part.get("id"))
        if part.get("geometry_level") != "NOMINAL_SKIN" or part.get("orientation") not in {"XY", "XZ"}:
            raise BackendError(f"Unsupported part geometry: {part.get('id')}")
        if part.get("qty", 1) != 1:
            raise BackendError("Each nominal part must be an explicit occurrence (qty=1)")
        for key in ("width", "height", "thickness", "x", "y", "z"):
            value = part.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise BackendError(f"Non-finite/non-numeric {key}: {part.get('id')}")
            if key in {"width", "height", "thickness"} and value <= 0:
                raise BackendError(f"Non-positive {key}: {part.get('id')}")
        # A caller must not add features that this rectangular adapter silently drops.
        allowed = {"id", "type_key", "kind", "bay", "band", "width", "height", "thickness", "x", "y", "z", "orientation", "geometry_level", "qty", "area_m2"}
        if set(part) - allowed:
            raise BackendError(f"Unsupported part fields: {sorted(set(part) - allowed)}")


@dataclass(frozen=True)
class Selection:
    requested: str
    selected: str
    python: str
    probe: dict
    unavailable: tuple[dict, ...] = ()

    def provenance(self) -> dict:
        return {"requested": self.requested, "selected": self.selected,
                "selection_policy": "explicit_availability_fallback" if self.requested == "auto" else "explicit_no_fallback",
                "runtime_python": self.python, "runtime": self.probe,
                "unavailable_candidates": list(self.unavailable),
                "adapter_contract": "nominal-box-panels-v1", "production_qualified": False}


def select_backend(requested: str = "cadquery", runtime_python: str | None = None, *, timeout: float = 45) -> Selection:
    if requested not in BACKENDS:
        raise BackendError(f"Unknown CAD backend {requested!r}; choose {BACKENDS}")
    # Resolve the executable without shell parsing. A command with arguments is not accepted.
    import shutil
    external_python = shutil.which(runtime_python) if runtime_python else sys.executable
    if not external_python:
        raise BackendError(f"Runtime Python does not exist: {runtime_python}")
    unavailable = []
    for candidate in (("cadgen", "build123d", "cadquery") if requested == "auto" else (requested,)):
        executable = sys.executable if candidate == "cadquery" else external_python
        try:
            result = _run([executable, "-I", str(WORKER), "probe", candidate], timeout=timeout)
            if result.returncode:
                raise BackendError(result.stderr.strip() or result.stdout.strip() or "runtime probe failed")
            probe = json.loads(result.stdout)
            if probe.get("provider") != candidate or probe.get("ok") is not True:
                raise BackendError("Invalid runtime probe response")
            return Selection(requested, candidate, executable, probe, tuple(unavailable))
        except (OSError, ValueError, BackendError) as exc:
            unavailable.append({"provider": candidate, "reason": str(exc)[-4000:]})
            if requested != "auto":
                raise BackendError(f"Requested backend {candidate!r} is unavailable: {exc}; no fallback attempted") from exc
    raise BackendError(f"No CAD backend is available: {unavailable}")


def _model_source(provider: str, step_name: str) -> str:
    # JSON input is data, never interpolated as Python. Labels are not code.
    imports = "from cadgen import build123d as bd\nfrom cadgen import step" if provider == "cadgen" else "import build123d as bd"
    decorator = f"@step(out={('../STEP/' + step_name)!r})\n" if provider == "cadgen" else ""
    output = "model()" if provider == "cadgen" else f"bd.export_step(model(), Path(__file__).parent / '../STEP/' / {step_name!r})"
    return f'''# Generated from immutable geometry_ir.json; edit configuration and regenerate.
from __future__ import annotations
import json
from pathlib import Path
{imports}

{decorator}def model():
    ir = json.loads((Path(__file__).parent / "../geometry_ir.json").read_text(encoding="utf-8"))
    parts = []
    for p in ir["parts"]:
        dimensions = (p["width"], p["height"], p["thickness"]) if p["orientation"] == "XY" else (p["width"], p["thickness"], p["height"])
        shape = bd.Box(*dimensions, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
        shape = shape.moved(bd.Location((p["x"], p["y"], p["z"])))
        shape.label = p["id"]
        parts.append(shape)
    return bd.Compound(children=parts, label=ir["project"])

if __name__ == "__main__":
    {output}
'''


def _readback(step: Path, ir: dict) -> dict:
    """Independently re-open every provider's actual saved STEP with compatibility OCP."""
    import cadquery as cq
    compound = cq.importers.importStep(str(step)).val()
    solids = compound.Solids()
    if len(solids) != len(ir["parts"]) or not compound.isValid() or any(not s.isValid() for s in solids):
        raise BackendError("STEP readback failed solid count or B-Rep validity")
    expected = []
    for p in ir["parts"]:
        dx, dy, dz = (p["width"], p["height"], p["thickness"]) if p["orientation"] == "XY" else (p["width"], p["thickness"], p["height"])
        expected.append((p["x"], p["y"], p["z"], dx, dy, dz, dx * dy * dz))
    actual = []
    for solid in solids:
        b = solid.BoundingBox()
        actual.append((b.xmin, b.ymin, b.zmin, b.xlen, b.ylen, b.zlen, solid.Volume()))
    # STEP may reorder occurrences; compare the full geometry signature, not position in file.
    def order(v): return tuple(round(x, 4) for x in v)
    for exp, got in zip(sorted(expected, key=order), sorted(actual, key=order)):
        if any(not math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-5) for a, b in zip(exp, got)):
            raise BackendError(f"Saved STEP differs from canonical nominal geometry: expected={exp}, actual={got}")
    bb = compound.BoundingBox()
    return {"solid_count": len(solids), "bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
            "valid": True, "invalid_solid_indices": [], "geometry_level": ir["geometry_level"],
            "volume_mm3": sum(s.Volume() for s in solids), "per_solid_geometry_verified": True,
            "saved_step_sha256": _digest(step), "readback_provider": "cadquery/OCP"}


def build_step(ir: dict, out: Path, *, selection: Selection | None = None,
               backend: str = "cadquery", runtime_python: str | None = None,
               requirements: list[str] | None = None, timeout: float = 180) -> dict:
    validate_capabilities(ir, requirements)
    original = json.dumps(ir, sort_keys=True, allow_nan=False)
    selected = selection or select_backend(backend, runtime_python)
    out = Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise BackendError(f"Refusing to overwrite an existing STEP: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    provenance = selected.provenance()
    source_bytes = None
    target_source = out.parent.parent / "SOURCE" / f"{out.stem}.py"
    if selected.selected != "cadquery" and (target_source.exists() or target_source.is_symlink()):
        raise BackendError(f"Refusing to overwrite model source: {target_source}")
    # All providers export to staging. Rejected geometry never enters the delivery.
    with tempfile.TemporaryDirectory(prefix="cadfab-runtime-") as tmp:
        root = Path(tmp)
        (root / "STEP").mkdir()
        generated = root / "STEP" / out.name
        if selected.selected == "cadquery":
            from .cadquery_backend import build_step as compatibility_build
            compatibility_build(copy.deepcopy(ir), generated)
            provenance["model_adapter_sha256"] = _digest(Path(__file__).with_name("cadquery_backend.py"))
        else:
            (root / "SOURCE").mkdir()
            ir_path = root / "geometry_ir.json"
            ir_path.write_text(json.dumps(ir, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            source = root / "SOURCE" / f"{out.stem}.py"
            source.write_text(_model_source(selected.selected, out.name), encoding="utf-8")
            env = dict(os.environ, CADGEN_DAEMON="0", CADGEN_CACHE_DIR=str(root / "cache"),
                       CADGEN_UPDATE_CHECK="0", DO_NOT_TRACK="1", MPLCONFIGDIR=str(root / "matplotlib"),
                       PYTHONDONTWRITEBYTECODE="1")
            command = [selected.python, "-I", str(source)]
            if selected.selected == "cadgen":
                command += ["--force", "--json"]
            result = _run(command, env=env, timeout=timeout)
            if result.returncode:
                raise BackendError(f"{selected.selected} build failed; no fallback attempted:\n{result.stderr[-8000:]}\n{result.stdout[-4000:]}")
            source_bytes = source.read_bytes()
            provenance.update({"model_source": str(target_source.relative_to(out.parent.parent)),
                               "model_source_sha256": _digest(source),
                               "export_api": "cadgen.step parameterless model" if selected.selected == "cadgen" else "build123d.export_step",
                               "runtime_stdout": result.stdout[-16000:], "runtime_stderr": result.stderr[-16000:]})
        if not generated.is_file() or generated.stat().st_size == 0:
            raise BackendError("Runtime reported success without producing the declared STEP")
        result = _readback(generated, ir)
        if json.dumps(ir, sort_keys=True, allow_nan=False) != original:
            raise BackendError("Canonical input was mutated during generation")
        # Exclusive creates preserve earlier artifacts even if another writer races us.
        if source_bytes is not None:
            target_source.parent.mkdir(parents=True, exist_ok=True)
            with target_source.open("xb") as handle:
                handle.write(source_bytes)
        with out.open("xb") as handle:
            handle.write(generated.read_bytes())
    result["provider"] = provenance
    return result
