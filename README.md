# saleae-tools

Agent-friendly tools for the Saleae Logic Pro 16, built for FPGA bring-up work
(Lattice ECP5 boards at 3.3 V: SPI, I2C, UART, JTAG, QSPI flash, USB FS).

The idea is the same as `kicad-tools` and `klayout-tools`: every command has a
machine-readable output, nothing needs a GUI click, and captures land in the
same viewer as the RTL simulation traces.

**Status: pre-alpha, 2026-09-21.** The export parsers and VCD bridge are tested
against synthetic files. `slt devices` and `slt capture --vcd --save` have been
run once against a Logic Pro 16 through Logic 2.4.46's automation server, and
`slt mcp-tools` against its MCP server (15 tools, listed in `docs/mcp.md`).

## What is here

| Piece | Depends on | Notes |
|---|---|---|
| `saleae_tools.binexport` | stdlib | Reads and writes Logic 2 binary exports, format versions 0 and 1, digital and analog. v0 files are exposed as single-chunk v1 so callers handle one shape. |
| `saleae_tools.vcd` | stdlib | `digital_*.bin` to one VCD for GTKWave / Surfer. Gaps between chunks render as `x`. |
| `saleae_tools.automation` | `logic2-automation` (extra) | Thin wrapper: connect or launch (GUI or the native headless preview), list devices, timed capture, binary export. |
| `saleae_tools.mcp` | stdlib | Enumerates the tools on Logic 2's built-in MCP server, since Saleae does not publish the list. |
| `slt` CLI | | `info`, `dump`, `vcd`, `devices`, `capture`, `mcp-tools`. |
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

# Same, but launch Saleae's native headless server instead of the GUI
slt capture --headless -o captures/run3 --channels 0-3 ...

# See what the Logic 2 MCP server offers (Settings > Automation > enable MCP server)
slt mcp-tools
```

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
extensions/         Logic 2 HLA extensions (empty for now)
```

MIT licensed.
