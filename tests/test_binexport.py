import array
import struct

import pytest

from saleae_tools import binexport as be


def _digital(version: int, chunks: int = 1) -> be.DigitalExport:
    out = be.DigitalExport(version)
    t = 0.0
    for i in range(chunks):
        trans = array.array("d", [t + 1e-6 * k for k in range(1, 5)])
        out.chunks.append(
            be.DigitalChunk(
                initial_state=i % 2,
                begin_time=t,
                end_time=t + 1e-5,
                transitions=trans,
                sample_rate=None if version == 0 else 500e6,
            )
        )
        t += 1e-3  # leave a gap between chunks
    return out


@pytest.mark.parametrize("version,chunks", [(0, 1), (1, 1), (1, 3)])
def test_digital_roundtrip(tmp_path, version, chunks):
    p = tmp_path / "digital_0.bin"
    src = _digital(version, chunks)
    be.write_digital(p, src)
    got = be.read_digital(p)
    assert got.version == version
    assert len(got.chunks) == chunks
    for a, b in zip(src.chunks, got.chunks, strict=True):
        assert a.initial_state == b.initial_state
        assert a.begin_time == b.begin_time
        assert a.end_time == b.end_time
        assert list(a.transitions) == list(b.transitions)
        assert a.sample_rate == b.sample_rate
    assert got.num_transitions == 4 * chunks
    assert be.sniff(p) == (version, "digital")


def test_digital_v0_header_bytes(tmp_path):
    """Pin the on-disk layout against the documented v0 offsets."""
    p = tmp_path / "d.bin"
    be.write_digital(p, _digital(0))
    raw = p.read_bytes()
    assert raw[:8] == b"<SALEAE>"
    assert struct.unpack_from("<ii", raw, 8) == (0, 0)
    initial, begin, end, n = struct.unpack_from("<IddQ", raw, 16)
    assert (initial, begin, n) == (0, 0.0, 4)
    assert end == pytest.approx(1e-5)
    assert len(raw) == 16 + 28 + 8 * 4


def test_states_alternate():
    c = _digital(0).chunks[0]
    states = [s for _, s in c.states()]
    assert states == [0, 1, 0, 1, 0]


@pytest.mark.parametrize("version,waves", [(0, 1), (1, 1), (1, 2)])
def test_analog_roundtrip(tmp_path, version, waves):
    p = tmp_path / "analog_0.bin"
    src = be.AnalogExport(version)
    for i in range(waves):
        src.waveforms.append(
            be.AnalogWaveform(
                begin_time=float(i),
                sample_rate=50e6,
                downsample=4,
                samples=array.array("f", [0.0, 1.5, 3.3, 1.5]),
                trigger_time=float(i) + 0.5 if version == 1 else None,
            )
        )
    be.write_analog(p, src)
    got = be.read_analog(p)
    assert got.version == version
    assert len(got.waveforms) == waves
    w = got.waveforms[0]
    assert list(w.samples) == pytest.approx([0.0, 1.5, 3.3, 1.5])
    assert w.effective_rate == pytest.approx(12.5e6)
    assert w.end_time == pytest.approx(3 / 12.5e6)
    assert w.time_of(2) == pytest.approx(2 / 12.5e6)
    if version == 1:
        assert w.trigger_time == pytest.approx(0.5)
    assert be.sniff(p) == (version, "analog")
    assert isinstance(be.read_export(p), be.AnalogExport)


def test_bad_magic(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"NOTSALEA" + b"\0" * 8)
    with pytest.raises(be.ExportFormatError, match="bad magic"):
        be.read_export(p)


def test_truncated(tmp_path):
    p = tmp_path / "x.bin"
    be.write_digital(p, _digital(0))
    p.write_bytes(p.read_bytes()[:-8])
    with pytest.raises(be.ExportFormatError, match="truncated"):
        be.read_digital(p)


def test_wrong_kind(tmp_path):
    p = tmp_path / "x.bin"
    be.write_digital(p, _digital(0))
    with pytest.raises(be.ExportFormatError, match="not analog"):
        be.read_analog(p)


def test_v0_multi_chunk_rejected(tmp_path):
    with pytest.raises(ValueError):
        be.write_digital(tmp_path / "x.bin", _digital(0, 2))


def test_level_at_boundaries():
    """``level_at`` applies transitions at or before ``t``."""
    c = _digital(0).chunks[0]  # initial 0, transitions at 1..4 us
    assert c.initial_state == 0
    assert list(c.transitions) == pytest.approx([1e-6, 2e-6, 3e-6, 4e-6])

    assert c.level_at(-1.0) == 0  # before begin_time
    assert c.level_at(c.begin_time) == 0  # exactly at begin_time
    assert c.level_at(0.5e-6) == 0  # between begin_time and the first transition
    assert c.level_at(1e-6) == 1  # exactly on a transition: it has been applied
    assert c.level_at(1.5e-6) == 1
    assert c.level_at(2e-6) == 0  # exactly on the second transition
    assert c.level_at(4e-6) == 0  # exactly on the last transition
    assert c.level_at(c.end_time) == 0  # after the last transition


def test_level_at_honours_initial_state():
    """A chunk starting high is the inverse of one starting low."""
    c = _digital(1, 2).chunks[1]
    assert c.initial_state == 1
    assert c.level_at(c.begin_time) == 1
    assert c.level_at(c.transitions[0]) == 0
    assert c.level_at(c.transitions[1]) == 1


def test_level_at_agrees_with_states():
    """Sampling just after each state change matches ``states()``."""
    c = _digital(0).chunks[0]
    for t, state in c.states():
        assert c.level_at(t + 1e-9) == state
