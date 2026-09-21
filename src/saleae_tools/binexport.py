"""Reader for the Logic 2 binary export format (versions 0 and 1).

The format is documented by Saleae:

* Version 0: https://www.saleae.com/support/logic-software/saving-and-exporting-data/binary-export-format-logic-2
* Version 1: https://www.saleae.com/support/logic-software/saving-and-exporting-data/binary-and-csv-export-formats-2025-update

Every file starts with a 16-byte header::

    byte[8]  identifier   "<SALEAE>"
    int32    version      0 or 1
    int32    type         0 = digital, 1 = analog

All multi-byte values are little-endian.

Digital v0 body::

    uint32   initial_state
    double   begin_time
    double   end_time
    uint64   num_transitions
    double[] transition_times

Digital v1 body: ``uint64 chunk_count`` followed by that many chunks, each::

    uint32   initial_state
    double   sample_rate
    double   begin_time
    double   end_time
    uint64   num_transitions
    double[] transition_times

Analog v0 body::

    double   begin_time
    uint64   sample_rate
    uint64   downsample
    uint64   num_samples
    float[]  voltages

Analog v1 body: ``uint64 waveform_count`` followed by that many waveforms, each::

    double   begin_time
    double   trigger_time
    double   sample_rate
    int64    downsample
    uint64   num_samples
    float[]  voltages

A v0 file is exposed as a v1 file with exactly one chunk / waveform so callers
only ever handle one shape. v0 digital files carry no sample rate, so
``DigitalChunk.sample_rate`` is ``None`` for them.
"""

from __future__ import annotations

import array
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal

MAGIC = b"<SALEAE>"
HEADER = struct.Struct("<8sii")
TYPE_DIGITAL = 0
TYPE_ANALOG = 1

_DIGITAL_V0 = struct.Struct("<IddQ")
_DIGITAL_V1_CHUNK = struct.Struct("<IdddQ")
_ANALOG_V0 = struct.Struct("<dQQQ")
_ANALOG_V1_WAVE = struct.Struct("<dddqQ")
_COUNT = struct.Struct("<Q")


class ExportFormatError(ValueError):
    """Raised when a file is not a Logic 2 binary export we understand."""


@dataclass
class DigitalChunk:
    """One contiguous run of digital samples on a single channel."""

    initial_state: int
    begin_time: float
    end_time: float
    transitions: array.array[float]  # typecode 'd', seconds, ascending
    sample_rate: float | None = None

    @property
    def num_transitions(self) -> int:
        return len(self.transitions)

    def states(self) -> list[tuple[float, int]]:
        """Return ``[(time, new_state), ...]`` starting with the initial state."""
        out = [(self.begin_time, self.initial_state)]
        s = self.initial_state
        for t in self.transitions:
            s ^= 1
            out.append((t, s))
        return out


@dataclass
class DigitalExport:
    version: int
    chunks: list[DigitalChunk] = field(default_factory=list)
    path: Path | None = None

    @property
    def begin_time(self) -> float:
        return self.chunks[0].begin_time if self.chunks else 0.0

    @property
    def end_time(self) -> float:
        return self.chunks[-1].end_time if self.chunks else 0.0

    @property
    def num_transitions(self) -> int:
        return sum(c.num_transitions for c in self.chunks)


@dataclass
class AnalogWaveform:
    begin_time: float
    sample_rate: float
    downsample: int
    samples: array.array[float]  # typecode 'f', volts
    trigger_time: float | None = None

    @property
    def num_samples(self) -> int:
        return len(self.samples)

    @property
    def effective_rate(self) -> float:
        """Samples per second after downsampling."""
        return self.sample_rate / self.downsample if self.downsample else self.sample_rate

    @property
    def end_time(self) -> float:
        if not self.samples or not self.effective_rate:
            return self.begin_time
        return self.begin_time + (self.num_samples - 1) / self.effective_rate

    def time_of(self, index: int) -> float:
        return self.begin_time + index / self.effective_rate


@dataclass
class AnalogExport:
    version: int
    waveforms: list[AnalogWaveform] = field(default_factory=list)
    path: Path | None = None

    @property
    def num_samples(self) -> int:
        return sum(w.num_samples for w in self.waveforms)


def _read_exact(f: BinaryIO, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise ExportFormatError(f"truncated file: wanted {n} bytes, got {len(b)}")
    return b


def _read_array(f: BinaryIO, typecode: Literal["d", "f"], count: int) -> array.array[float]:
    a: array.array[float] = array.array(typecode)
    if count:
        a.frombytes(_read_exact(f, count * a.itemsize))
        if sys.byteorder != "little":
            a.byteswap()
    return a


def read_header(f: BinaryIO) -> tuple[int, int]:
    """Return ``(version, type)`` after consuming the 16-byte header."""
    magic, version, kind = HEADER.unpack(_read_exact(f, HEADER.size))
    if magic != MAGIC:
        raise ExportFormatError(f"bad magic {magic!r}; not a Logic 2 binary export")
    if version not in (0, 1):
        raise ExportFormatError(f"unsupported export version {version}")
    if kind not in (TYPE_DIGITAL, TYPE_ANALOG):
        raise ExportFormatError(f"unknown export type {kind}")
    return version, kind


def sniff(path: str | Path) -> tuple[int, Literal["digital", "analog"]]:
    """Return ``(version, kind)`` for a file without reading its body."""
    with open(path, "rb") as f:
        version, kind = read_header(f)
    return version, ("digital" if kind == TYPE_DIGITAL else "analog")


def _read_digital_body(f: BinaryIO, version: int) -> list[DigitalChunk]:
    chunks: list[DigitalChunk] = []
    if version == 0:
        initial, begin, end, n = _DIGITAL_V0.unpack(_read_exact(f, _DIGITAL_V0.size))
        chunks.append(DigitalChunk(initial, begin, end, _read_array(f, "d", n)))
        return chunks
    (count,) = _COUNT.unpack(_read_exact(f, _COUNT.size))
    for _ in range(count):
        initial, rate, begin, end, n = _DIGITAL_V1_CHUNK.unpack(
            _read_exact(f, _DIGITAL_V1_CHUNK.size)
        )
        chunks.append(DigitalChunk(initial, begin, end, _read_array(f, "d", n), rate))
    return chunks


def _read_analog_body(f: BinaryIO, version: int) -> list[AnalogWaveform]:
    waves: list[AnalogWaveform] = []
    if version == 0:
        begin, rate, down, n = _ANALOG_V0.unpack(_read_exact(f, _ANALOG_V0.size))
        waves.append(AnalogWaveform(begin, float(rate), down, _read_array(f, "f", n)))
        return waves
    (count,) = _COUNT.unpack(_read_exact(f, _COUNT.size))
    for _ in range(count):
        begin, trig, rate, down, n = _ANALOG_V1_WAVE.unpack(_read_exact(f, _ANALOG_V1_WAVE.size))
        waves.append(AnalogWaveform(begin, rate, down, _read_array(f, "f", n), trig))
    return waves


def read_digital(path: str | Path) -> DigitalExport:
    path = Path(path)
    with open(path, "rb") as f:
        version, kind = read_header(f)
        if kind != TYPE_DIGITAL:
            raise ExportFormatError(f"{path} is an analog export, not digital")
        return DigitalExport(version, _read_digital_body(f, version), path)


def read_analog(path: str | Path) -> AnalogExport:
    path = Path(path)
    with open(path, "rb") as f:
        version, kind = read_header(f)
        if kind != TYPE_ANALOG:
            raise ExportFormatError(f"{path} is a digital export, not analog")
        return AnalogExport(version, _read_analog_body(f, version), path)


def read_export(path: str | Path) -> DigitalExport | AnalogExport:
    """Read either kind of export, dispatching on the header."""
    path = Path(path)
    with open(path, "rb") as f:
        version, kind = read_header(f)
        if kind == TYPE_DIGITAL:
            return DigitalExport(version, _read_digital_body(f, version), path)
        return AnalogExport(version, _read_analog_body(f, version), path)


# --- writers: used by tests and for synthesising fixtures without hardware ---


def write_digital(path: str | Path, export: DigitalExport) -> None:
    with open(path, "wb") as f:
        f.write(HEADER.pack(MAGIC, export.version, TYPE_DIGITAL))
        if export.version == 0:
            if len(export.chunks) != 1:
                raise ValueError("v0 digital export holds exactly one chunk")
            c = export.chunks[0]
            f.write(_DIGITAL_V0.pack(c.initial_state, c.begin_time, c.end_time, c.num_transitions))
            f.write(_le_bytes(c.transitions))
            return
        f.write(_COUNT.pack(len(export.chunks)))
        for c in export.chunks:
            if c.sample_rate is None:
                raise ValueError("v1 digital chunks need a sample_rate")
            f.write(
                _DIGITAL_V1_CHUNK.pack(
                    c.initial_state, c.sample_rate, c.begin_time, c.end_time, c.num_transitions
                )
            )
            f.write(_le_bytes(c.transitions))


def write_analog(path: str | Path, export: AnalogExport) -> None:
    with open(path, "wb") as f:
        f.write(HEADER.pack(MAGIC, export.version, TYPE_ANALOG))
        if export.version == 0:
            if len(export.waveforms) != 1:
                raise ValueError("v0 analog export holds exactly one waveform")
            w = export.waveforms[0]
            f.write(_ANALOG_V0.pack(w.begin_time, int(w.sample_rate), w.downsample, w.num_samples))
            f.write(_le_bytes(w.samples))
            return
        f.write(_COUNT.pack(len(export.waveforms)))
        for w in export.waveforms:
            f.write(
                _ANALOG_V1_WAVE.pack(
                    w.begin_time,
                    w.trigger_time if w.trigger_time is not None else w.begin_time,
                    w.sample_rate,
                    w.downsample,
                    w.num_samples,
                )
            )
            f.write(_le_bytes(w.samples))


def _le_bytes(a: array.array[float]) -> bytes:
    if sys.byteorder == "little":
        return a.tobytes()
    b = array.array(a.typecode, a)
    b.byteswap()
    return b.tobytes()
