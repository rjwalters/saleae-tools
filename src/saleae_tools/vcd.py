"""Write digital exports as a VCD file for GTKWave / Surfer.

The point is to put a bench capture next to a Verilator or cocotb trace in the
same viewer. Times are quantised to the VCD timescale (default 1 ns; the Logic
Pro 16 samples at up to 500 MS/s, so 1 ns loses nothing).

Gaps between v1 chunks are rendered as ``x`` so a viewer shows where the
capture had no data rather than a stale level.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from saleae_tools.binexport import DigitalExport

_TIMESCALES = {"1s": 1, "1ms": 1e-3, "1us": 1e-6, "1ns": 1e-9, "1ps": 1e-12}

# VCD identifier codes: printable ASCII, one or more chars. 94 single-char
# codes cover far more than 16 channels, but be general anyway.
_ID_CHARS = [chr(c) for c in range(33, 127)]


def _id_code(i: int) -> str:
    code = ""
    while True:
        code = _ID_CHARS[i % len(_ID_CHARS)] + code
        i = i // len(_ID_CHARS) - 1
        if i < 0:
            return code


def _events(export: DigitalExport, unit: float, t0: float) -> Iterable[tuple[int, str]]:
    """Yield ``(tick, value)`` for one channel, values in ``{"0","1","x"}``."""
    prev_end: int | None = None
    for c in export.chunks:
        begin = round((c.begin_time - t0) / unit)
        if prev_end is not None and begin > prev_end:
            yield prev_end, "x"
        s = c.initial_state
        yield begin, str(s)
        for t in c.transitions:
            s ^= 1
            yield round((t - t0) / unit), str(s)
        prev_end = round((c.end_time - t0) / unit)
    if prev_end is not None:
        yield prev_end, "x"


def write_vcd(
    out: TextIO | str | Path,
    exports: Sequence[DigitalExport],
    names: Sequence[str] | None = None,
    timescale: str = "1ns",
    module: str = "saleae",
    origin: float | None = None,
) -> int:
    """Write ``exports`` (one per channel) to ``out``. Returns event count.

    ``names`` defaults to ``ch<N>``. ``origin`` is the capture time mapped to
    VCD tick 0; it defaults to the earliest ``begin_time`` across channels.
    """
    if timescale not in _TIMESCALES:
        raise ValueError(f"timescale must be one of {sorted(_TIMESCALES)}")
    unit = _TIMESCALES[timescale]
    if names is None:
        names = [f"ch{i}" for i in range(len(exports))]
    if len(names) != len(exports):
        raise ValueError("names and exports differ in length")
    if origin is None:
        origin = min((e.begin_time for e in exports if e.chunks), default=0.0)

    if isinstance(out, str | Path):
        with open(out, "w") as f:
            return write_vcd(f, exports, names, timescale, module, origin)

    ids = [_id_code(i) for i in range(len(exports))]
    out.write(f"$date {datetime.now(UTC).isoformat()} $end\n")
    out.write("$version saleae-tools $end\n")
    out.write(f"$timescale {timescale} $end\n")
    out.write(f"$scope module {module} $end\n")
    for name, code in zip(names, ids, strict=True):
        out.write(f"$var wire 1 {code} {name} $end\n")
    out.write("$upscope $end\n$enddefinitions $end\n")

    # k-way merge of per-channel event streams; ties keep channel order.
    streams = [
        ((tick, i, v) for tick, v in _events(e, unit, origin)) for i, e in enumerate(exports)
    ]
    current_tick: int | None = None
    count = 0
    for tick, i, v in heapq.merge(*streams):
        if tick != current_tick:
            out.write(f"#{tick}\n")
            current_tick = tick
        out.write(f"{v}{ids[i]}\n")
        count += 1
    return count
