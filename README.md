# saleae-tools

Agent-friendly tools for the Saleae Logic Pro 16, built for FPGA bring-up work
(Lattice ECP5 boards at 3.3 V: SPI, I2C, UART, JTAG, QSPI flash, USB FS).

The idea is the same as `kicad-tools` and `klayout-tools`: every command has a
machine-readable output, nothing needs a GUI click, and captures land in the
same viewer as the RTL simulation traces.

**Status: pre-alpha, 2026-09-22.** Fixed board-1 probe profiles, edge-triggered
capture with a timeout, decoded CSV, named VCD, saved-capture re-export and
run manifests are ready for iCEPi bench work.
SPI/UART/I²C analyzer setup and exports have been exercised through Logic
2.4.46 with a Logic Pro 16; the FPGA has not arrived, so protocol traffic and
board wiring remain unverified. Parsers, timing measurements and lifecycle
error handling have synthetic/mock tests. The MCP server exposes 15 tools,
listed in `docs/mcp.md`.

Start with the [iCEPi + Raspberry Pi bring-up guide](docs/bringup.md) and the
editable [bench profiles](examples/).

## What is here

| Piece | Depends on | Notes |
|---|---|---|
| `saleae_tools.binexport` | stdlib | Reads and writes Logic 2 binary exports, format versions 0 and 1, digital and analog. v0 files are exposed as single-chunk v1 so callers handle one shape. |
| `saleae_tools.vcd` | stdlib | `digital_*.bin` to one VCD for GTKWave / Surfer. Gaps between chunks render as `x`. |
| `saleae_tools.automation` | `logic2-automation` (extra) | Connect or launch, list devices, timed/edge-triggered capture, binary export. |
| `saleae_tools.profile` / `session` | stdlib / automation extra for live runs | TOML signal maps and analyzer settings; capture/export bundles with run metadata and artifact hashes. |
| `saleae_tools.timing` | stdlib | Complete pulse widths and like-edge periods, excluding chunk gaps and partial boundary pulses. |
| `saleae_tools.mcp` | stdlib | Enumerates the tools on Logic 2's built-in MCP server, since Saleae does not publish the list. |
| `slt` CLI | | `info`, `dump`, `vcd`, `timing`, `devices`, `capture`, `export`, `mcp-tools`. |
| [`docs/survey.md`](docs/survey.md) | | The open source landscape as of 2026-09-21, with the reasoning behind the choices above. |

## Install

```bash
uv sync --extra dev --extra automation   # development
pip install 'saleae-tools[automation]'    # once published
```

## Use

```bash
# Describe exports Logic 2 wrote (File > Export raw data > binary)
slt info captures/run1/digital_*.bin --json

# Bundle 16 channels into one VCD, named in channel order
slt vcd captures/run1/digital_*.bin -o run1.vcd --names sclk,mosi,miso,cs_n,...

# Talk to a running Logic 2 (Settings > Automation > enable automation server)
slt devices
slt capture -o captures/run2 --channels 0,1,2,3 --rate 100000000 --seconds 0.5 --vcd

# Validate the UART probe map without connecting to Logic 2
slt capture --profile examples/icepi-uart.toml --dry-run

# Capture/decode UART, with named VCD, .sal, and a run.json manifest
slt capture --profile examples/icepi-uart.toml -o captures/uart-001 --vcd --save --json

# Offline timing measurements (JSON, seconds)
slt timing captures/uart-001/digital_6.bin

# Trigger on board-1's event marker, saving all 16 channels and decoded buses
uv run python scripts/capture-board.py --note 'test=bringup; RTL=<commit>'

# Or trigger on SPI chip select without an FPGA event marker
uv run python scripts/capture-board.py --protocol spi --trigger cs_n --edge falling

# Re-export a saved capture through Logic 2, without a connected Saleae
slt export captures/uart-001/capture.sal --profile examples/icepi-uart.toml \
  -o captures/uart-001-redecode --vcd

# Same, but launch Saleae's native headless server instead of the GUI
slt capture --headless -o captures/run3 --channels 0-3 --seconds 0.5 --vcd

# See what the Logic 2 MCP server offers (Settings > Automation > enable MCP server)
slt mcp-tools
```

Capture/export directories must be new or empty. `--note` records firmware
revision, test case and wiring in `run.json`; `--json` prints that manifest.
`--headless` requires the preview client described in the survey; the regular
PyPI client uses the running GUI automation server.

## Enabling the servers in Logic 2

Both are off by default and both are toggled in the GUI:
**Settings > Automation** (or the Automation button in the bottom bar).

| Server | Port | Client |
|---|---|---|
| Automation (gRPC) | 10430 | `logic2-automation`, this package |
| MCP (Streamable HTTP) | 10530 | `claude mcp add --transport http logic2 http://127.0.0.1:10530` |

The native headless server (no Electron, no display) is a preview from
2026-08-08. See `docs/survey.md` for where to get it.

## Layout

```
src/saleae_tools/   package
tests/              synthetic-fixture tests, no hardware needed
docs/               survey and notes
examples/           editable iCEPi probe maps and analyzer profiles
scripts/            board capture helper with unique run directories
extensions/         Logic 2 HLA extensions (empty for now)
```

MIT licensed.
