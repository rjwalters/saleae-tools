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
- `.mcp.json` registers Logic 2's MCP server as `logic2` at project scope.
  The `claude` shell wrapper on this machine fails in non-interactive
  shells (`_claude_build_argv: command not found`), so edit the JSON directly.

<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.12.2 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
