# Historical Stage 1 repository workflow verification, 2026-10-08

The logs, acceptance report, counts and binary hashes in this directory are historical evidence for the earlier Stage 1 repository workflow. They are not results for the current Stage 2 source. Only [source-manifest.json](source-manifest.json) is maintained as the current repository source-byte verification manifest. Updating that manifest does not requalify these older logs. Fresh Stage 2 build/test reports are created under each unique ignored `artifacts/workbuddy-runs/<run>/` directory by [WORKBUDDY.md](../../docs/WORKBUDDY.md); see [the first-integration scope](../../docs/STAGE2-LOCAL.md). The old files one level above are historical as well.

## Historical actual checks (not current Stage 2 qualification)

- Linux .NET SDK 8.0.425: locked restore; Release build, 0 warnings and 0 errors; official pinned RhinoCommon/Eto compilation.
- Core: 37/37 automated fake-adapter tests passed.
- Host: 52/52 real loopback HTTP-process tests passed.
- Release gate: 83 regression assertions passed, including canonical POSIX/Windows path ordering, shuffled inputs, Unicode and preservation of the original 46-file Linux digest.
- Repository evidence helper: 15 tests passed, including candidate/source tampering, log failure, path escape, unknown commit, missing live evidence and reinitialization rejection.
- PowerShell 7.4.7 on Linux: all four scripts parse; 15/15 native helper tests passed. The actual `workbuddy-build.ps1 -CrossBuild` workflow completed, including locked win-x64 framework-dependent Host publish, plugin collection, fresh local evidence and gate exit 2. This is stronger than a static review but is not Windows qualification.
- PowerShell 7.4.7 on Linux: `workbuddy-verify.ps1` rechecked source/candidate bytes and propagated expected release gate exit 2. Its retained logs are under `verification/`.
- Candidate binary hashes are recorded in [candidate-SHA256.json](candidate-SHA256.json). Generated binaries are not committed; WorkBuddy builds them from source.

## Not run / blocked

Windows PowerShell 5.1, PowerShell 7 on Windows, actual Windows candidate execution and licensed Windows/Rhino UI acceptance have NOT_RUN status. F-02 through F-11 and all L cases remain NOT_RUN in this cloud build. Full Stage 1 is BLOCKED. The production status is REVIEW and is never promoted by this gate.

## Recheck

From the module root:

```sh
python3 -X utf8 scripts/test_release_gate.py
python3 -X utf8 scripts/test_workbuddy_evidence.py
python3 -X utf8 scripts/workbuddy_evidence.py verify-source --source-root .
python3 -X utf8 scripts/release_gate.py evidence/repository-workflow/acceptance.json --source-root .
```

The final command must return 2 while the recorded live checks have not run. It is not a build failure and must not be changed to PASS. For a new Windows run use [WORKBUDDY.md](../../docs/WORKBUDDY.md), not these committed historical logs. The new per-run `acceptance.local.json` and `live-cases.json` live only under that run's artifacts directory.

## Tool provenance

Portable PowerShell was fetched only from the official [PowerShell v7.4.7 release](https://github.com/PowerShell/PowerShell/releases/tag/v7.4.7), with `powershell-7.4.7-linux-x64.tar.gz` SHA-256 `cfd57927b7a0d9f2da400471ea8dadc3ceb52f5e4a4a9a51c20495b4071f055a` verified against its official hashes. It was extracted to an isolated temporary cloud directory; no user workstation or global settings were changed. These runtime files are not part of the repository.
