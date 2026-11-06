"""Offline UART decoding of digital exports, independent of Logic 2."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

from saleae_tools.binexport import DigitalChunk, DigitalExport


@dataclass
class Frame:
    time_s: float  # falling edge of the start bit
    byte: int
    framing_error: bool
    parity_error: bool


@dataclass
class Decoded:
    frames: list[Frame] = field(default_factory=list)
    truncated: int = 0  # frames cut off by the end of a chunk; never decoded


def _level(chunk: DigitalChunk, t: float) -> int:
    return chunk.initial_state ^ (bisect_right(chunk.transitions, t) & 1)


def decode(
    export: DigitalExport,
    baud: float,
    *,
    bits: int = 8,
    parity: str = "none",
    stop_bits: int = 1,
    idle_high: bool = True,
) -> Decoded:
    """Decode UART frames (LSB first). Each chunk is decoded independently.

    A frame whose last sampled bit lies past ``chunk.end_time`` is dropped and
    counted in ``truncated`` instead of being decoded from missing data.
    """
    if baud <= 0:
        raise ValueError("baud must be positive")
    if parity not in ("none", "even", "odd"):
        raise ValueError("parity must be none, even or odd")
    if bits < 1 or stop_bits < 1:
        raise ValueError("bits and stop_bits must be >= 1")
    idle = 1 if idle_high else 0
    bit_s = 1.0 / baud
    n_parity = 0 if parity == "none" else 1
    n_bits = 1 + bits + n_parity + stop_bits
    out = Decoded()
    for chunk in export.chunks:
        ts = chunk.transitions
        floor = float("-inf")  # ignore edges at or before the previous frame's last sample
        for i, t0 in enumerate(ts):
            # State after transition i; a start bit is an edge away from idle.
            if t0 <= floor or (chunk.initial_state ^ ((i + 1) & 1)) == idle:
                continue
            last_sample = t0 + (n_bits - 0.5) * bit_s
            if last_sample > chunk.end_time:
                out.truncated += 1
                break
            sample = [_level(chunk, t0 + (k + 0.5) * bit_s) for k in range(n_bits)]
            data = sample[1 : 1 + bits]
            value = sum((b ^ (1 - idle)) << k for k, b in enumerate(data))
            parity_error = False
            if n_parity:
                ones = bin(value).count("1") + (sample[1 + bits] ^ (1 - idle))
                parity_error = (ones % 2 == 1) if parity == "even" else (ones % 2 == 0)
            framing_error = any(b != idle for b in sample[1 + bits + n_parity :])
            out.frames.append(Frame(t0, value, framing_error, parity_error))
            floor = last_sample
    return out


def match_expected(stream: list[int], pattern: list[int]) -> dict[str, object]:
    """Check that ``pattern`` repeats through ``stream`` from its first occurrence.

    A trailing partial repetition is accepted. ``mismatch_offset`` is an index
    into ``stream``; it is None when the pattern matched or was never found.
    """
    n = len(pattern)
    if n == 0:
        raise ValueError("expected pattern is empty")
    start = next((i for i in range(len(stream) - n + 1) if stream[i : i + n] == pattern), None)
    if start is None:
        return {"matched": False, "start_offset": None, "mismatch_offset": None, "repeats": 0}
    for i in range(start, len(stream)):
        if stream[i] != pattern[(i - start) % n]:
            return {
                "matched": False,
                "start_offset": start,
                "mismatch_offset": i,
                "repeats": (i - start) // n,
            }
    return {
        "matched": True,
        "start_offset": start,
        "mismatch_offset": None,
        "repeats": (len(stream) - start) // n,
    }
