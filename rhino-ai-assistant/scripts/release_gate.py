#!/usr/bin/env python3
"""Fail closed on missing/failed acceptance. Headless tests cannot imply live Rhino acceptance."""
import argparse
import hashlib
import json
import pathlib

REQUIRED = [f"F-{i:02}" for i in range(1, 13)]
LIVE = set(REQUIRED) - {"F-01", "F-12"}
VALID = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
EXCLUDED = {"bin", "obj", ".git", "artifacts", "evidence", "dist", "__pycache__"}


def canonical_entries(entries):
    """Order relative POSIX names case-sensitively, independent of Path platform.

    Hash JSON is UTF-8 with ASCII escapes, compact comma/colon delimiters, and
    [relative-path, file-sha256] pairs. File bytes are never newline-normalized.
    """
    return sorted(((name.as_posix() if hasattr(name, "as_posix") else str(name), digest)
                   for name, digest in entries), key=lambda row: row[0])


def source_entries(root):
    root = pathlib.Path(root)
    return canonical_entries((path.relative_to(root), hashlib.sha256(path.read_bytes()).hexdigest())
                             for path in root.rglob("*")
                             if path.is_file() and not any(part in EXCLUDED for part in path.relative_to(root).parts))


def digest_entries(entries):
    return hashlib.sha256(json.dumps(canonical_entries(entries), ensure_ascii=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def source_digest(root):
    return digest_entries(source_entries(root))


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
            references = row.get("evidence", [])
            if not isinstance(references, list) or any(not isinstance(r, str) for r in references):
                blockers.append(f"{key}: evidence must be a list of relative filenames")
                continue
            for reference in references:
                file = (evidence_root / reference).resolve()
                if not file.is_relative_to(evidence_root.resolve()) or not file.is_file() or file.stat().st_size == 0:
                    blockers.append(f"{key}: missing or invalid evidence file {reference}")
    if report.get("production_status") != "REVIEW":
        blockers.append("Stage 1 cannot grant production approval")
    return blockers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", default="evidence/acceptance.json")
    parser.add_argument("--source-root", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent.parent,
                        help="Module source root; evidence filenames are relative to this root.")
    args = parser.parse_args(argv)
    try:
        report = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8-sig"))
        blockers = evaluate(report, args.source_root.resolve())
    except (OSError, ValueError, TypeError, AttributeError) as exc:
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
