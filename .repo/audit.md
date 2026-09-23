# Repository hygiene — 2026-09-22

Ran the default `repo:all` workflow from Repo Skills v0.12.2 (`75ebbee`).
Installed its Codex and Claude Code surfaces before the pass; it had not
previously been installed in this repository.

- **Audit:** no unresolved Markdown links or skill command references; no
  orphan candidates among project scripts/data. The existing root README and
  bring-up guide cover the small source, examples and documentation directories.
  No additional directory READMEs are needed for this pass.
- **Gitignore:** added `/.squad/` for the local SQLite coordination database
  and its WAL/SHM files. The installer also ignores its machine-local metadata.
  Captures, environments and caches remain ignored; their contents were kept.
- **Scrub:** inspected a fresh normal clone of origin at `1744665` (5 reachable
  commits, 39 HEAD files, 50 unique history blobs), commit metadata/messages,
  and the new installer payload. Heuristic checks found no credentials or
  sensitive identifiers at HEAD. Fourteen history-only email occurrences are
  confined to commit metadata/messages. Known example/noreply addresses,
  checksum-context IDs, SSH GitHub remote syntax and generic path/network
  examples were treated as benign. GitHub returned no issues, PRs, issue
  comments or review comments. Forks/hidden PR refs were not scanned; affiliated
  entity matching is unconfigured. This is not a comprehensive security audit.
- **Docs:** documented the installed maintenance workflow and why its upstream
  copies are excluded from package Ruff checks. Existing capture examples and
  fixed harness assignments remain consistent with the implementation.
- **Tidy:** no disposable junk found. Kept `.venv/`, tool caches, `.squad/`,
  capture data and tracked scaffolding; no files, branches, worktrees or stashes
  were removed.
- **Tools:** Repo Skills matches the source remote at `75ebbee`; its resync
  dry run reports 51 unchanged files and no drift.
- **Dependencies (read-only):** no Renovate/Dependabot configuration or bot
  activity found; no open dependency PRs. No deployed organization policy or
  Renovate preset was found at `rjwalters/.github` (404). Vulnerability alerts
  are disabled (dedicated endpoint 404); automated security fixes are disabled
  (`enabled: false`). The alert-list endpoint was unavailable (403), so no
  claim is made about outstanding vulnerabilities. Dependency-graph SBOM was
  unavailable (404), and GitHub App installation was not verified. Automerge
  is off; no release-age policy is configured locally. Configuring the updater
  and alerting is deferred to a dedicated dependency setup task.
- **Validation:** `uv sync --extra dev --extra automation`, Ruff lint/format,
  mypy and all 117 tests pass. The preceding capture commit also passed all
  four GitHub CI jobs (macOS/Ubuntu, Python 3.12/3.13).
- **Git baseline:** only `main`, one worktree, no stashes. Maintenance changes
  are committed and pushed with this report; no pruning was needed.

The separate bench follow-up remains live trigger completion/timeout cleanup
verification once Logic 2's API is responsive and the iCEPi hardware is wired.
