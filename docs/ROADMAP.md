# saleae-tools roadmap

Agent-friendly tools for the Saleae Logic Pro 16: read Logic 2 exports, bridge
them to VCD, drive captures without a GUI click, and assert on what was
captured, for FPGA bring-up work.

Status as of 2026-11-13, `main` @ `b96e689`.

`WORK_PLAN.md` is a generated view of tracker labels; this file says what comes
next and why, using the build order in [`survey.md`](survey.md) and the five
bench stages in [`bringup.md`](bringup.md).

## Where it stands

Done, with tests that need no hardware (`tests/`, CI on macOS and Ubuntu,
Python 3.12 and 3.13, `.github/workflows/ci.yml`):

- **Build step 1, export parser and VCD bridge.** `binexport.py`, `vcd.py`;
  `slt info`, `slt dump`, `slt vcd`.
- **Build step 2, capture and re-export over the automation API.**
  `automation.py`, `profile.py`, `session.py`; `slt devices`, `slt capture`,
  `slt export`; TOML profiles in `examples/`; `run.json` manifests with
  artifact hashes. Smoke-tested once against a real Logic Pro 16 through
  Logic 2.4.46 on flat probe inputs (`bringup.md`, "Validation before hardware
  arrival").
- **Edge-triggered capture** with pre/post windows and a bounded wait, plus
  `scripts/capture-board.py`. Covered by a synthetic gRPC server; the live API
  timed out on 2026-09-22, so a live trigger run is still owed.
- **Offline measurement and assertion verbs.** `slt timing` (`timing.py`),
  `slt uart --expect` (`uart.py`, PR #8, bench stage 3) and `slt spi --expect`
  (`spi.py`, PR #13, bench stage 4). All three are synthetic-tested only.
- **Build step 4, MCP.** `slt mcp-tools` lists Logic 2's MCP tools;
  `docs/mcp.md` records the 15 found.

Not done:

- **No capture of real protocol traffic has been verified.** Every decoder
  result so far comes from exports written by `binexport.write_digital`.
- **Bench stages 1, 2 and 5** (pin-through, loader, I2C) have probe profiles in
  `examples/` but no offline check that can pass or fail a capture.
- **Build step 5** (headless server) and **build step 6** (`extensions/`, which
  holds only `.gitkeep`) have not started.
- The package is `0.1.0` in `pyproject.toml`, with no tag and no release.

The tracker has no open work item: the one open issue (#21) is an
automatically maintained digest, and there are no open pull requests.

## Now

Each can start today, fits one pull request, needs no hardware and follows
the pattern of `uart.py` and `spi.py`: a stdlib-only module, fixtures from
`binexport.write_digital`, a `slt` verb that prints JSON and exits 1 on a
failed assertion. None has an issue yet.

1. **Offline I2C decoder and `slt i2c --expect` (bench stage 5).**
   Done when `src/saleae_tools/i2c.py` decodes START, repeated START, STOP,
   address, read/write bit, data bytes and ACK/NACK from SCL and SDA exports,
   `slt i2c` asserts an expected transaction, and `tests/test_i2c.py` passes
   in CI. Blocked by: nothing.
2. **Offline clocked-serial decoder for the loader (bench stage 2).**
   The loader is "custom synchronous serial", so no stock analyzer covers it.
   Done when a `slt` verb decodes fixed-width words (16-bit, MSB-first by
   default) from a clock and a data export while an enable signal is at its
   active level, asserts expected words, and has synthetic tests for word
   boundaries and a partial trailing word. Blocked by: nothing.
3. **Limits on `slt timing` so a measurement can fail a run.**
   `slt timing` always exits 0, and `bringup.md` lists timing masks as
   follow-on work. Done when the verb accepts minimum and maximum bounds for
   high pulse, low pulse and period, reports each violated bound in its JSON,
   exits 1 on a violation or on an empty distribution that a bound was set
   for, and has tests for both. Blocked by: nothing.
4. **Measured bit time and drift in `slt uart` (bench stage 3).**
   Stage 3 asks for "bit-width and frame drift against the reference test";
   the decoder samples at the nominal baud and reports neither. Done when the
   report carries the measured bit time, its error against `--baud`, and the
   worst per-frame sampling drift, with an optional tolerance that exits 1
   when exceeded, and tests using a deliberately off-rate synthetic stream.
   Blocked by: nothing.

## Next

5. **Pin-through check (bench stage 1).** A verb that confirms an output
   export follows an input export by the expected number of clock edges and
   that reset forces the expected output level. Unblocked by item 2, which
   supplies the clock-edge sampling this needs.
6. **Profile-driven offline decode.** `slt uart`, `slt spi` and the new verbs
   take `--profile` plus a run directory and resolve channels and analyzer
   settings from the TOML, instead of repeating `--channels 0,1,2,3` and
   `--baud`. Done when each example profile in `examples/` decodes a synthetic
   run directory in a test. Unblocked by items 1 and 2, so the option lands on
   every decoder at once.
7. **Assertion results in `run.json`.** `bringup.md` is explicit that
   `status: "complete"` does not mean the contents passed. Done when a run
   can record the offline check that was applied and its outcome next to the
   artifact hashes. Unblocked by item 6.
8. **Refresh the README status paragraph and `survey.md` build order**, both
   dated 2026-09-22. Done when both describe the UART, SPI and Now-item
   verbs. Unblocked by the Now items landing, so it is written once.

## Later

- **Simulation alignment.** Compare a capture VCD against a simulation VCD
  from a shared reset or marker edge. Question first: is a stdlib VCD reader
  enough, and what tolerance model is right when the capture is sampled at
  10 ns and the simulation is cycle-exact?
- **HLA extensions in `extensions/` (build step 6).** Question first: with
  offline decoders in the package, which bench protocols still need an
  in-viewer decoder, and can one share its core with the offline module?
- **`slt decode` through libsigrokdecode.** Question first: which bench
  protocol do neither Logic 2 nor the offline decoders here cover?
- **First tagged release and PyPI publication.** Question first: what is the
  minimum bench-verified surface that justifies moving off pre-alpha?

## Blocked and waiting

- **Everything that needs the bench.** Verifying pin assignments, capturing
  real UART, SPI, I2C and loader traffic, and the live edge-trigger run all
  wait on the FPGA board and its wrapper gateware (`bringup.md`).
- **Build step 5, the headless server.** It needs Saleae's preview server and
  preview client fetched onto a machine with the analyzer attached
  (`survey.md`, "Native headless server"); it cannot be done from a
  hardware-free worker.

The four Now items are dispatchable today; the rest is sequenced or waiting.

## Not planned

- A replacement capture driver. `survey.md` records that the sigrok driver for
  this analyzer is digital-only and experimental; capture stays on Logic 2's
  automation API.
