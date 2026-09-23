# iCEPi + Raspberry Pi bench workflow

Updated 2026-09-22 for the incoming iCEPi Zero. The Saleae workflow is ready
for bench use; FPGA pin assignments, gateware and protocol correctness still
need validation on the board.

## Start with UART and a repeating FPGA pattern

Keep the Logic Pro 16 attached to the Mac running Logic 2. Use the Raspberry
Pi to coordinate programming, reset and UART traffic. Start with a repeating
pattern in the FPGA so a short timed capture includes traffic, without
depending on Linux/SSH scheduling to start a transaction at the right instant.

| Component | First job |
|---|---|
| Raspberry Pi | Coordinate the test; send/receive UART bytes once the interface is routed |
| iCEPi | Run the DUT and an initial repeating test pattern |
| Saleae + Mac | Observe physical pins, decode, save raw data and VCD |
| RTL simulation | Supply expected bytes and cycle counts for the same test case |

The board's [upstream repository](https://github.com/cheyao/icepi-zero)
identifies it as an ECP5 board and documents onboard USB JTAG/UART support.
Use its hardware files for the **received PCB revision** and the FPGA
wrapper's LPF to assign pins. A USB UART route can avoid Pi header setup if
the chosen gateware exposes it. Otherwise enable a free Pi UART with its
serial console disabled. Check the Pi model: `/dev/serial0` can refer to the
Pi 5 debug connector instead of the GPIO header. See the
[Raspberry Pi UART documentation](https://www.raspberrypi.com/documentation/computers/configuration.html#configuring-uarts).

The emulator specification calls for **controller** SPI and I²C. A MOSI→MISO
loopback is a useful first SPI receive check; a separate FPGA responder or a
known peripheral can follow. For I²C, use a known target or a small FPGA
target with physical open-drain pins and pull-ups. Pi `spidev` is normally
the controller side, so using it as the emulator's SPI responder needs a
different setup; see the [Pi SPI documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#serial-peripheral-interface-spi).

## Probe assignments

Plan of record: **board-1 is the instrumented reference**, with the same
header assignments on all five Pi Zero 2 W + iCEPi boards. The Logic Pro 16
stays on the Mac and taps board-1's signals. Probing a bus does not consume
additional GPIO. All profiles use this fixed harness; changing protocols
does not require moving probes. The FPGA wrapper/LPF still needs to implement
these assignments for the received board revision before wiring is validated.

The numbers in `examples/*.toml` are **Saleae channel numbers**, not physical
header pins, BCM GPIO numbers, or FPGA package pads:

| Saleae | Signal | Physical header pin | Pi BCM GPIO | Intended role |
|---|---|---|---|---|
| D0 | `sclk` | 23 | 11 | SPI clock |
| D1 | `mosi` | 19 | 10 | SPI controller → target |
| D2 | `miso` | 21 | 9 | SPI target → controller |
| D3 | `cs_n` | 24 | 8 | SPI chip select, active low |
| D4 | `scl` | 5 | 3 | I²C clock, open drain |
| D5 | `sda` | 3 | 2 | I²C data, open drain |
| D6 | `uart_tx` | 10 | 15 | FPGA → Pi RX |
| D7 | `uart_rx` | 8 | 14 | Pi TX → FPGA |
| D8 | `rst_n` | 11 | 17 | Pi → DUT reset, active low |
| D9 | `ena` | 13 | 27 | Pi → DUT enable |
| D10 | `mode` | 15 | 22 | Pi → program-loader mode (`ui_in[7]`) |
| D11 | `serial_data` / `ui_in_0` | 16 | 23 | Pi → loader data / pin-through input |
| D12 | `clk` | 18 | 24 | Slow DUT clock or output clock monitor; select one driver per test |
| D13 | `event` | 22 | 25 | FPGA → test-start/event marker; Pi input |
| D14 | `error` | 29 | 5 | FPGA → error/status; Pi input |
| D15 | `uo_out_0` | 31 | 6 | FPGA → pin-through output / spare debug; Pi input |

Connect Saleae ground to a header ground (for example physical pin 6), using
short ground leads near signals where practical. Start with D0–D7 and ground;
add D8–D15 as their gateware is implemented. Keep physical pins 27/28
(GPIO0/1) available for Pi HAT identification. Header numbering is supported
by the [Pi GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)
and the [iCEPi v1.3 PCB](https://github.com/cheyao/icepi-zero/blob/main/hardware/v1.3/icepi-zero.kicad_pcb).
D8–D15's functions are our wrapper plan, not existing iCEPi firmware features.

For the emulator's SPI/I²C **controller** tests, disable the Pi's controller
drivers on those pins and leave them as inputs. Use a loopback, FPGA responder
or peripheral as described above. Pi-generated SPI/I²C traffic is appropriate
when the FPGA runs a target/responder design. UART remains available for Pi
coordination. Never enable two push-pull drivers on a shared net.

Power plan: remove **physical contacts 1 and 17 from the inter-board riser**
to separate the boards' regulated 3.3 V outputs. Supply the Pi through its
micro-USB power input from the planned 5 V / 4 A PoE supply, and feed iCEPi
through header pins 2/4 plus common ground. Both boards still generate their
own 3.3 V. The 4 A supply rating does not establish the rating of the Pi's
connector/cable/PCB path; verify voltage under the combined load. On v1.3,
USB VBUS and header 5 V are directly connected, so a powered USB cable to
another computer introduces another supply onto that rail.

This is our circuit-based stacking plan, pending received-revision checks:
the [iCEPi maintainer confirms 5 V input](https://github.com/cheyao/icepi-zero/issues/29#issuecomment-4495522851),
and the [Pi HAT guide prohibits external power on its 3.3 V header pins](https://github.com/raspberrypi/hats/blob/master/designguide.md#back-powering-the-pi-via-the-gpio-header).
We found no explicit iCEPi instruction to remove contacts 1/17. Saleae needs
signal and ground connections, not a connection to either 3.3 V supply pin.

Verify bank voltage and signal directions. `threshold_v = 3.3` selects
Saleae's 3.3 V logic preset for a verified 3.3 V bank; it does not set a
literal 3.3 V comparator trip point. I²C needs pull-ups and open-drain drivers.

`icepi-board.toml` records all 16 channels and decodes SPI mode 0, I²C and
115200 8N1 UART. Other profiles select only their bus/control channels plus
D13. The pin-through profile calls D11 `ui_in_0`; the loader and board
profiles call that same wire `serial_data`.

`uart_tx`/`uart_rx` are named from the DUT's perspective. Start at a slow
test clock for the pin-through and loader checks. At 100 MS/s each sample
is 10 ns; a 50 MHz clock only gets two samples per cycle, insufficient for
useful margin measurements. Use a supported higher Saleae rate with fewer
channels when needed, and record it. Digital captures do not measure analog
rise time or prove metastability margins.

## Capture, decode, inspect

Run from this checkout on the Mac. Enable Logic 2's **automation server** in
Settings > Automation (10430); the MCP toggle (10530) is independent.

```bash
uv sync --extra dev --extra automation
uv run slt devices --json

# Resolve channel references and validate without hardware or file writes.
uv run slt capture --profile examples/icepi-uart.toml --dry-run

# With repeating UART traffic already running on the FPGA:
uv run slt capture --profile examples/icepi-uart.toml \
  -o captures/uart-001 --save --vcd --json \
  --note 'RTL revision + bitstream hash; firmware test; board revision; wiring'

# Pulse widths and periods from exports, with no Logic 2 dependency:
uv run slt timing captures/uart-001/digital_6.bin

# Re-decode an existing .sal with edited analyzer settings; no device needed.
uv run slt export captures/uart-001/capture.sal \
  --profile examples/icepi-uart.toml -o captures/uart-001-redecode --vcd --json
```

Each output directory must be new or empty. A run writes:

- `digital_<n>.bin`: raw data for the selected channels.
- `decoded.csv`: Logic 2's analyzer data table, when the profile has analyzers.
- `capture.vcd`: named traces with `--vcd`; open alongside simulation in Surfer/GTKWave.
- `capture.sal`: original capture plus configured analyzers, with `--save`.
- `run.json`: status, resolved profile, requested acquisition settings, versions,
  selected device, user note, and SHA-256 hashes of the completed artifacts.

## Triggered acquisition

Run this on the Mac to capture the next rising edge of the **FPGA event marker
on D13 / header pin 22**, followed by 50 ms of data:

```bash
uv run python scripts/capture-board.py --dry-run
uv run python scripts/capture-board.py --note 'test=uart-55; RTL=<commit>; bitstream=<sha256>'

# Before the marker exists, use SPI chip-select assertion instead:
uv run python scripts/capture-board.py --protocol spi --trigger cs_n --edge falling

# DUT reset release, keeping 20 ms before and 100 ms after:
uv run python scripts/capture-board.py --trigger rst_n --pre .02 --post .1

# Collect three separate transactions, rearming between runs:
uv run python scripts/capture-board.py --count 3 --timeout 60
```

The helper saves binary exports, decoded CSV, `.sal`, VCD and `run.json` under
`captures/board-1/<UTC timestamp>-<protocol>-<run>/`. `--board board-2` changes
the recorded identity/output path when the probes are moved; it does not
select a board electronically. `--device` selects a Saleae when several are
connected. Failures stop a repeated series; already completed runs remain.
There are gaps while exporting and rearming, so this is not lossless streaming.

Wait for **"Capture started"** before initiating a Pi test in another terminal.
This reports Logic 2's successful start response; its API exposes no separate
hardware-ready acknowledgement. Allow the requested prehistory to accumulate
before the event. The FPGA wrapper should hold D13 low at idle and raise it
just before the transaction (a pulse at least 1 μs wide is a useful initial
convention). Keep Pi GPIO25 an input. Once triggered, later edges do not
restart that capture. Gateware must implement the marker before using it.

Equivalent CLI, useful in your own scripts:

```bash
uv run slt capture --profile examples/icepi-spi.toml \
  --trigger cs_n --edge falling --pre .01 --post .05 --timeout 30 \
  -o captures/spi-trigger-001 --save --vcd --json
```

`[trigger]` in a TOML profile accepts `signal`, `edge` (`rising`/`falling`),
`pre_trigger_s`, `post_trigger_s`, and `timeout_s`. The trigger signal must be
in `[signals]`; the dry run validates this without the SDK or hardware. CLI
options override those fields. `--timed --seconds .1` disables a profile's
trigger. `--seconds` otherwise applies only to timed capture.

The timeout covers waiting for the edge **and completing post-trigger data**,
not exports. On timeout the command exits nonzero, attempts to close the
capture, writes `status: "timeout"`, and exports no successful capture bundle.
If cleanup fails, the error and manifest say to check Logic 2. Setup/cleanup
RPCs also have deadlines. Ctrl-C cancels the wait and attempts cleanup.
`capture_started_at` records the host start acknowledgement, not the sampled
trigger timestamp. `status: "complete"` means acquisition/export completed,
not that protocol contents passed an assertion.

Prehistory is requested using Saleae's total-window trimming; it is not a
guarantee of that many seconds before an early trigger. The capture buffer is
256 MB; high transition density or a long wait can exhaust it and fail the
run. Logic 2 can round recording windows. Trigger handling uses the SDK's
`WaitCapture` gRPC call with a deadline because SDK 1.0.11's public `wait()`
has no timeout parameter. It never combines `wait()` with `stop()`; see the
[Saleae capture API](https://saleae.github.io/logic2-automation/automation.html#saleae.automation.Capture.wait).

Check `status == "complete"`. A failed/interrupted run can leave partial
artifacts and a `failed` manifest; a trigger timeout produces `timeout`.
A process killed abruptly can leave
`running`. Neither is evidence of a successful capture. A complete run means
the files were produced, **not** that their decoded contents pass a test.
Record the RTL/bitstream/firmware identity explicitly with `--note`; the tool
does not infer what is programmed into the FPGA. Captures under `captures/`
are gitignored.

Acquisition settings in the manifest are the requested settings. Logic 2
can round capture duration; `slt info`/`slt timing` report exported bounds.
When re-exporting `.sal`, `acquisition` is `null`: profile rate/duration do
not describe the original capture. Only channel selection, names and decoder
settings are applied. Loading and conversion go through Logic 2's API.

`timing` always prints JSON, in seconds. High/low pulse statistics include
only intervals bounded by two observed edges. Leading/trailing partial
levels and gaps between chunks are excluded. Rising/falling periods are
calculated within chunks and can include idle time between transactions.
Empty distributions have count 0 and null min/max/mean; they must not be
interpreted as a passing timing check or a baud estimate.

## Profile format

See [the SPI example](../examples/icepi-spi.toml) for a complete profile.
`version = 1` is required. `[signals]` maps unique identifier names to distinct
channels 0–15. `[capture]` holds `sample_rate`, `duration_s`, and `threshold_v`.
`[[analyzers]]` supplies the exact Logic 2 analyzer name and a unique label.
`[analyzers.channels]` maps analyzer setting names to signal names;
`[analyzers.settings]` holds literal dropdown values, bit rates and flags.
Use the channels table for channel selection so it is validated against the
probe map. Logic 2 validates analyzer names, dropdown choices and supported
sample-rate/channel combinations when the run executes.

`--rate`, `--seconds` and `--threshold` override capture settings in a
profile. Edit `[signals]` to change a profile's wiring; `--channels` and
`--names` cannot be combined with `--profile`. Without a profile,
`--channels 10,0-2 --names cs_n,sclk,mosi,miso` associates names in the given
order; VCD output sorts the pairs by channel number. Default acquisition
without a profile remains channels 0–3, 100 MS/s, 1 second, 3.3 V preset.
An explicit `--device` is required if multiple real Saleaes are connected or
if using a simulation device. Offline commands and `--dry-run` need no SDK.

Analyzer settings follow Saleae's
[API documentation](https://saleae.github.io/logic2-automation/automation.html)
and analyzer settings sources:
[SPI](https://github.com/saleae/spi-analyzer/blob/master/src/SpiAnalyzerSettings.cpp),
[Async Serial](https://github.com/saleae/serial-analyzer/blob/master/src/SerialAnalyzerSettings.cpp),
[I²C](https://github.com/saleae/i2c-analyzer/blob/master/src/I2cAnalyzerSettings.cpp).
The UART profile is 115200, 8N1; change both TX and RX bit rates together.
For SPI modes 1–3, change the CPOL/CPHA dropdowns to match the firmware.

## Protocol-emulator milestones

These are bench acceptance tasks, not implemented firmware or passing results.
The inspected emulator checkout was commit
`420c370994deff79f18849113b0d2a6985d47715`. Its top level was still a registered
pin-through stub; the program-loader RTL existed separately. The
[target specification](https://github.com/2AMLogic/sg13cmos5l-protocol-emulator/blob/420c370994deff79f18849113b0d2a6985d47715/spec/target-spec.md)
and [ISA decision record](https://github.com/2AMLogic/sg13cmos5l-protocol-emulator/blob/420c370994deff79f18849113b0d2a6985d47715/spec/decision-records/0001-isa.md)
are the source for the intended tests:

| Stage | Exercise | Observe |
|---|---|---|
| 1: pin-through | Slow clock, repeated input pattern, reset and enable | Reset output state, registered input-to-output behavior, stable probe mapping |
| 2: loader | Reset with MODE=`ui_in[7]` high; shift known 16-bit words MSB-first on `ui_in[0]`; lower MODE | Clock/data/mode/reset sequence, word boundaries; correlate readback with the RTL test |
| 3: UART | Repeating `55 00 ff` at 115200 8N1, then 9600–1 Mbaud cases | Expected bytes, framing/parity errors, bit-width and frame drift against the reference test |
| 4: SPI | Known bytes, initially slow, then modes 0–3 and SCLK up to f_clk/4 | CS boundaries, both data directions, CPOL/CPHA, high/low times |
| 5: I²C | Known target address/data at 100 kHz, then 400 kHz | START/repeated START/STOP, ACK/NACK, high/low and setup/hold intervals |

The loader is custom synchronous serial, so its example has no stock SPI
analyzer. Core readback/internal state still needs an exposed debug path or
a test wrapper; raw pin captures alone do not establish that program memory
was written correctly.

Automation supports timed and edge-triggered captures with a bounded trigger
wait. Remote stimulus orchestration, protocol-aware byte assertions, timing
masks and automated simulation alignment remain follow-on work. VCD tick
zero is the earliest exported sample;
align bench and simulation using a shared reset or marker signal rather than
assuming both clocks started together.

## Validation before hardware arrival

On 2026-09-21, Logic 2.4.46 with `logic2-automation` 1.0.11 and the connected
Logic Pro 16 completed a timed SPI-profile run, binary/CSV/VCD/`.sal` exports,
then `.sal` reloads with the UART and I²C analyzer profiles. These were flat
probe inputs: analyzer configuration and export compatibility were checked,
but no protocol payload, FPGA timing or physical pin assignment was verified.
Synthetic-file tests cover pulse measurements, chunk gaps, profile validation,
channel/name pairing, run manifests and cleanup on export errors.

On 2026-09-22, the fixed harness and trigger workflow passed 117 tests,
including a local synthetic gRPC server exercising actual WaitCapture
completion/deadlines. Ruff lint/format and mypy passed. Logic 2's live API
timed out during device discovery, so hardware trigger completion and cleanup
after a missing physical edge still need a bench check when the API responds.
