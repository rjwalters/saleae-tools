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
