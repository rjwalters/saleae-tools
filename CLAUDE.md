# saleae-tools — agent notes

- Core package is stdlib-only by design. Put anything that imports
  `saleae.automation` behind a lazy import in `saleae_tools/automation.py`.
- `uv sync --extra dev --extra automation`, then `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`, `uv run pytest -q`. CI runs
  exactly that on macOS and Ubuntu, Python 3.12 and 3.13.
- Tests use synthetic exports written by `binexport.write_digital/write_analog`.
  Never commit captures; `*.bin`, `*.sal`, `*.vcd`, `*.csv` are gitignored.
  Deliberate fixtures go under `tests/fixtures/` with a `!` rule.
- Hardware-dependent verbs (`slt devices`, `slt capture`) need Logic 2 with
  Settings > Automation > automation server enabled (port 10430). The MCP
  server is a separate toggle (port 10530).
- `docs/survey.md` is the landscape as of 2026-09-21. Update it, do not fork it.
- Give Logic 2 ABSOLUTE paths for exports and `.sal` saves. It resolves
  relative paths against its own cwd, which is a read-only disk image when
  macOS runs the app translocated (quarantined bundle). `export_binary`
  already resolves; keep it that way.
- `.sal` files are zip archives (`meta.json` + per-channel `digital-N.bin` in
  an undocumented internal layout, not the export format). Convert through
  the automation API (`load_capture` then export) rather than unzipping.
- `.mcp.json.bench` holds Logic 2's MCP server (`logic2`, `http://127.0.0.1:10530`).
  It is not named `.mcp.json` so fleet workers, which have no Logic 2, don't
  load it. On the bench, start Claude with `--mcp-config .mcp.json.bench`.
  The `claude` shell wrapper on this machine fails in non-interactive
  shells (`_claude_build_argv: command not found`), so edit the JSON directly.

<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.25.10 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.

Work is coordinated through `loom:` labels on issues and pull requests, and the same roles run either under `loom-daemon` or by hand in an attended session — daemon mode is optional. Create the labels once with `.loom/scripts/sync-labels.sh` (an install ships `.github/labels.yml` but does not create the labels on the forge). A pull request ready for review carries `loom:review-requested`; Judge reviews it and applies `loom:pr` (approved) or `loom:changes-requested`; Doctor fixes a `loom:changes-requested` pull request and returns it to `loom:review-requested`. Only a `loom:pr` pull request gets merged, and always via this repo's merge script (`.loom/scripts/merge-pr.sh`) — never a raw forge merge command such as `gh pr merge`. Full state machine: `.loom/docs/label-state-machine.md`.
<!-- END LOOM ORCHESTRATION -->
