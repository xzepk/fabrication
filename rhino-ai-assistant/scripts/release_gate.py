#!/usr/bin/env python3
"""Fail closed on missing/failed acceptance. Passing tests cannot imply live Rhino acceptance."""
import hashlib
import json
import pathlib
import sys

REQUIRED = [f"F-{i:02}" for i in range(1, 13)]
LIVE = set(REQUIRED) - {"F-01", "F-12"}
VALID = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}

def source_digest(root):
    excluded = {"bin", "obj", ".git", "artifacts", "evidence", "dist", "__pycache__"}
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not any(part in excluded for part in relative.parts):
            entries.append((relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()

def evaluate(report, evidence_root=None):
    blockers = []
    rows = report.get("checks", {})
    for key in REQUIRED:
        row = rows.get(key, {})
        status = row.get("status")
        if status not in VALID:
            blockers.append(f"{key}: missing or invalid status")
        elif status != "PASS":
            blockers.append(f"{key}: {status} — {row.get('reason', 'no acceptance evidence')}")
        if status == "PASS":
            if not row.get("evidence"):
                blockers.append(f"{key}: PASS lacks evidence")
            if key in LIVE and row.get("execution") != "live-windows-rhino":
                blockers.append(f"{key}: fake/headless evidence cannot satisfy live gate")
    env = report.get("live_environment", {})
    if any(rows.get(key, {}).get("status") == "PASS" for key in LIVE):
        for field in ("windows_version", "rhino_version", "runtime_version", "source_digest", "reviewer"):
            if not env.get(field):
                blockers.append(f"Live environment missing {field}")
    if evidence_root is not None:
        actual_digest = source_digest(evidence_root)
        if report.get("source_digest") != actual_digest:
            blockers.append("Acceptance source digest does not match current source files")
        if any(rows.get(key, {}).get("status") == "PASS" for key in LIVE) and env.get("source_digest") != actual_digest:
            blockers.append("Live evidence source digest does not match current source files")
        for key, row in rows.items():
            if row.get("status") != "PASS":
                continue
            for reference in row.get("evidence", []):
                file = (evidence_root / reference).resolve()
                if not file.is_relative_to(evidence_root.resolve()) or not file.is_file() or file.stat().st_size == 0:
                    blockers.append(f"{key}: missing or invalid evidence file {reference}")
    # Stage 1 gate never grants engineering production status.
    if report.get("production_status") != "REVIEW":
        blockers.append("Stage 1 cannot grant production approval")
    return blockers

def main():
    path = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "evidence/acceptance.json")
    try:
        report = json.loads(path.read_text())
        blockers = evaluate(report, path.resolve().parent.parent)
    except (OSError, ValueError, TypeError) as exc:
        print(f"BLOCKED: unreadable acceptance evidence: {exc}")
        return 2
    if blockers:
        print("STAGE 1 RELEASE BLOCKED")
        print("\n".join(blockers))
        return 2
    print("STAGE 1 TECHNICAL ACCEPTANCE PASSED; engineering production status remains REVIEW")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
