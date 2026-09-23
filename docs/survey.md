# Open source support for the Saleae Logic Pro 16 — survey, 2026-09-21

Machine at time of writing: macOS 27, Apple Silicon, Logic 2.4.46 running
(from a translocated `Saleae Logic.app`, not `/Applications`), Logic Pro 16
enumerated on USB (vendor 0x21A9 "Saleae", product "Logic Pro"). At the initial
survey neither the automation port (10430) nor the MCP port (10530) was
listening: both are opt-in toggles in the GUI. Later on the same day both
were enabled; real-device capture and MCP enumeration were exercised.

## Summary

There are three ways to drive this instrument from code. Only one of them is
worth building on.

| Route | What it gives | Verdict |
|---|---|---|
| **Saleae's own Logic 2 + automation surface** (gRPC API, native headless server, MCP server, Python HLA extensions, C++ Analyzer SDK, documented binary export) | Full hardware capability: 500 MS/s digital, analog, hardware trigger, all built-in decoders. Apache-2.0 client. | **Build here.** Everything the FPGA work needs is reachable without a GUI click, after a one-time toggle. |
| **sigrok `saleae-logic-pro` driver** | Fully open capture stack, but experimental, digital only, software trigger only, and needs firmware blobs extracted from Logic 1.2.10. | Not for capture. libsigrokdecode's ~130 decoders remain useful on exported data. |
| **Community parsers / MCP wrappers** | Small, mostly single-purpose. | Read for reference; superseded by Saleae's own MCP and by our parser. |

The two things that changed the picture recently:

1. **Native headless automation server** (preview, announced 2026-08-08 on
   Saleae's forum). A standalone binary plus `logic2_automation` 1.1.0 wheels
   for macOS arm64/x86_64, Linux x64/arm64, Windows x64. Same gRPC API, no
   Electron, no xvfb. `Manager.launch(headless=True)`. Supports Logic 8,
   Logic Pro 8, Logic Pro 16 (Logic MSO added 2026-08-20). Not on PyPI as of
   this survey; wheels and server zips are linked from the thread. This is
   what makes a CI or agent loop practical.
2. **Built-in MCP server** in Logic 2 (experimental). Streamable HTTP on
   `127.0.0.1:10530`, enabled under Settings > Automation. Saleae's pitch is
   exactly our loop: write RTL/firmware, flash, capture, decode, verify. The
   tool list is not published; `slt mcp-tools` asks the server.

## Saleae-provided surfaces

### Automation API (gRPC)

- Repo: https://github.com/saleae/logic2-automation (Apache-2.0). Proto file
  plus Python client. Docs: https://saleae.github.io/logic2-automation/ and
  https://docs.saleae.com/automation/guides/getting-started
- PyPI `logic2-automation` 1.0.11 (2025-11-18), requires Python >= 3.7.
  Verified installing and importing on Python 3.14 here (grpcio 1.84,
  protobuf 7.36).
- Needs Logic 2 >= 2.3.56. Server enabled in Settings > Automation, or by
  launching with `--automation` (`--automationPort N` to move it).
- Capabilities: list devices (real and simulated), start capture (timed,
  manual, digital trigger), device config (channels, sample rates, digital
  threshold volts), add analyzers, export raw CSV/binary, export analyzer
  data tables, save/load `.sal`.
- Java client by a third party: https://github.com/pfroud/saleae-logic2-automation-java

### Native headless server (preview)

- Thread: https://discuss.saleae.com/t/headless-logic2-automation-support/3793
- `logic2_automation-1.1.0-py3-none-macosx_11_0_arm64.whl` and matching
  server zips. Windows needs drivers, Linux needs udev rules.
- Public docs lag the preview; expect breaking changes.

### MCP server

- Marketing page: https://www.saleae.com/mcp. Docs:
  https://docs.saleae.com/mcp/guides/getting-started
- Enable in Settings > Automation. Register:
  `claude mcp add --transport http logic2 http://127.0.0.1:10530`
- Devices: Logic 8, Logic Pro 8, Logic Pro 16. Status experimental.
- Whether it works against the headless server is not documented.

### Extensions (Python) and Analyzer SDK (C++)

- HLA / measurement extensions: https://github.com/saleae/logic2-extensions.
  Two files (`extension.json` + Python). Logic 2 >= 2.2.6. Examples:
  https://github.com/saleae/hla-i2c-transactions,
  https://github.com/adafruit/Logic2-SPIFlash,
  https://github.com/kasjer/saleae_spiflash (QSPI, updated 2026-08).
  Our own protocol decoders (e.g. a SPI register map on a test harness) go
  here, in `extensions/`.
- Low-level analyzers: https://github.com/saleae/AnalyzerSDK (CMake, ships
  `lib_arm64`), template https://github.com/saleae/SampleAnalyzer, example
  https://github.com/oxidecomputer/8b10bAnalyzer. Source for Saleae's stock
  analyzers is downloadable but licensed only for use with Saleae products
  (not OSI). Only needed for bit-level protocols the stock set lacks.

### File formats

- Binary export v0 (all current non-MSO devices) and v1 (MSO, chunked, adds
  sample rate / trigger time):
  https://www.saleae.com/support/logic-software/saving-and-exporting-data/binary-export-format-logic-2
  https://www.saleae.com/support/logic-software/saving-and-exporting-data/binary-and-csv-export-formats-2025-update
  Implemented in `saleae_tools.binexport` with round-trip tests.
- `.sal` capture files are undocumented by policy
  (https://www.saleae.com/support/logic-software/saving-and-exporting-data/sal-file-format).
  Convert through the automation API (`load_capture` then export).
- Saleae's open source position (USB/device layer stays closed):
  https://www.saleae.com/support/tutorials-learning/concepts/saleae-open-source-support

### Distribution

- Homebrew cask `saleae-logic` 2.4.46 (macOS >= 12). The running copy on this
  machine is translocated, i.e. launched from a DMG; installing the cask
  gives a stable `/Applications` path for `Manager.launch()`.

## sigrok

- Driver `saleae-logic-pro`, shared with Logic Pro 8:
  https://sigrok.org/wiki/Saleae_Logic_Pro_16
- Digital only, 500 MHz at 4 channels, 100 MHz at 16, software trigger only,
  "experimental". Firmware (FX3 + FPGA bitstream) must be extracted from
  Saleae Logic 1.2.10 with `sigrok-fwextract-saleae-logic16`.
- Driver sources: https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic-pro
- OpenTraceLab is a sigrok fork that lists the device; its page 404'd during
  this survey.
- Worth keeping: `sigrok-cli` with libsigrokdecode can decode our exported
  data (VCD input) with protocol decoders Saleae lacks. That is a possible
  `slt decode` verb later; it does not need the driver.

## Community tools

| Project | What | Notes |
|---|---|---|
| https://github.com/znuh/saleae-binparser | C parser for digital binary export | GPL-2.0, Linux/FreeBSD, ~21 GiB in 30 s. Reference for a fast path if Python is ever too slow. |
| https://github.com/idaholab/Saleae_Output_Parser | Python export post-processing | INL. |
| https://github.com/AkiyukiOkayasu/saleae-logic2-automation-mcp | Rust MCP server over the gRPC API, 20+ tools | MIT/Apache-2.0. Predates Saleae's built-in MCP; useful as a tool-design reference. |
| https://github.com/themadinventor/jtaglogic | JTAG analyzer | Logic 1 era, 2017. Logic 2 has JTAG built in. |
| https://github.com/topics/saleae-logic | Topic index | |

## Alternative hardware, for the record

DSLogic U3Pro16 (DreamSourceLab) ships with DSView, an open sigrok fork:
https://tomverbeure.github.io/2025/04/12/DSLogic-U3Pro16-Teardown.html.
Not needed; the Logic Pro 16 plus the routes above covers the job.

## What this repo builds, in order (updated 2026-09-22)

1. **Export parser + VCD bridge** (done, synthetic tests). Bench captures next
   to Verilator/cocotb traces in Surfer or GTKWave.
2. **Capture and re-export over the automation API** (real Logic Pro 16
   smoke-tested through Logic 2.4.46). Named TOML profiles, UART/SPI/I²C
   analyzer tables, raw/VCD/`.sal` artifacts, settings and hashes in `run.json`.
   `slt export` loads `.sal` through the API; `slt timing` measures complete
   pulses offline. No iCEPi traffic has been verified yet.
3. **iCEPi + Raspberry Pi bring-up**: confirm wrapper pin assignments, start
   with pin-through and repeating UART traffic, then loader/SPI/I²C tests.
   See [the bench workflow](bringup.md) and `examples/`. Board-1 is the reference
   for a fixed 16-channel harness shared by five boards. Edge-triggered captures
   now have pre/post window settings, a bounded wait, and timestamped bundles
   via `scripts/capture-board.py`. Trigger completion/timeouts have synthetic
   gRPC tests; the live API timed out on 2026-09-22, so live trigger validation
   remains pending. Remote stimulus coordination and protocol assertions are
   follow-on work.
4. **MCP** (done): Logic 2 registered, 15 tools recorded in `docs/mcp.md`.
5. **Headless server** in CI on the Mac captain (pending): fetch the 1.1.0
   preview, `slt capture --headless`. Current bench work uses the GUI server.
6. **HLA extensions** for the bench protocols in `extensions/`, then possibly
   `slt decode` via libsigrokdecode for protocols Saleae lacks.
