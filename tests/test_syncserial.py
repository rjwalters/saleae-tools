import array
from pathlib import Path

import pytest

from saleae_tools.binexport import DigitalChunk, DigitalExport, write_digital
from saleae_tools.cli import main
from saleae_tools.syncserial import decode

SLOT = 4.0  # time units per bit
# Channel numbers from examples/icepi-loader.toml, in (clk, data, enable) order.
CHANNELS = (12, 11, 10)


def _bits(word, bits, msb_first):
    order = range(bits - 1, -1, -1) if msb_first else range(bits)
    return [(word >> k) & 1 for k in order]


def _signals(
    groups,
    *,
    bits=16,
    msb_first=True,
    edge="rising",
    enable_active_high=True,
    drop_last_bits=0,
    cut=False,
    clock_outside_enable=False,
):
    """Build (clk, data, enable) exports; groups is a list of word lists.

    One enable interval per group. Per bit slot the clock rises at +1 and falls
    at +3; data is set at +0 for ``edge="rising"`` and at +2 for
    ``edge="falling"``, so decoding with the other edge samples the wrong slot.
    """
    idle, active = (0, 1) if enable_active_high else (1, 0)
    trans: dict[str, list[float]] = {"clk": [], "data": [], "en": []}
    level = {"clk": 0, "data": 0, "en": idle}

    def set_(name, lvl, at):
        if level[name] != lvl:
            trans[name].append(at)
            level[name] = lvl

    def clock_slot(at, data_bit=None):
        if data_bit is not None:
            set_("data", data_bit, at + (2 if edge == "falling" else 0))
        set_("clk", 1, at + 1)
        set_("clk", 0, at + 3)

    t = 10.0
    for words in groups:
        if clock_outside_enable:  # must not be collected into any interval
            clock_slot(t, 1)
            t += SLOT
        set_("en", active, t)
        wbits = [b for w in words for b in _bits(w, bits, msb_first)]
        if drop_last_bits:
            wbits = wbits[:-drop_last_bits]
        t += SLOT
        for b in wbits:
            clock_slot(t, b)
            t += SLOT
        t += SLOT
        if cut:  # enable never deasserts before the chunk ends
            break
        set_("en", idle, t)
        t += SLOT
        if clock_outside_enable:
            clock_slot(t, 1)
            t += SLOT
        t += 2 * SLOT
    end = t + SLOT

    def ch(init, name):
        return DigitalExport(1, [DigitalChunk(init, 0.0, end, array.array("d", trans[name]), 1e6)])

    return ch(0, "clk"), ch(0, "data"), ch(idle, "en")


def _write(directory: Path, sig):
    for num, export in zip(CHANNELS, sig, strict=True):
        write_digital(directory / f"digital_{num}.bin", export)
    return directory


def test_two_16_bit_words():
    r = decode(*_signals([[0xA5A5, 0x1234]]))
    assert r.truncated == 0 and r.leftover_bits == 0
    assert [t.mosi for t in r.transactions] == [[0xA5A5, 0x1234]]
    assert r.transactions[0].miso is None


def test_partial_trailing_word_is_leftover_not_padded():
    r = decode(*_signals([[0xA5A5, 0xFFFF]], drop_last_bits=5))
    assert [t.mosi for t in r.transactions] == [[0xA5A5]]
    assert r.leftover_bits == 11 and r.truncated == 0


def test_enable_gate_excludes_clock_edges_outside_the_interval():
    r = decode(*_signals([[0xA5A5]], clock_outside_enable=True))
    assert [t.mosi for t in r.transactions] == [[0xA5A5]]
    assert r.leftover_bits == 0 and r.truncated == 0


def test_falling_edge_sampling():
    sig = _signals([[0xBEEF]], edge="falling")
    r = decode(*sig, edge="falling")
    assert [t.mosi for t in r.transactions] == [[0xBEEF]]
    assert r.leftover_bits == 0
    # The rising edge of the same capture samples the previous slot's data.
    assert decode(*sig).transactions[0].mosi != [0xBEEF]


def test_interval_cut_by_chunk_end_is_truncated():
    r = decode(*_signals([[0xA5A5]], cut=True))
    assert r.truncated == 1 and r.transactions == []


def test_multiple_intervals_are_separate_groups():
    r = decode(*_signals([[0xA5A5, 0x1234], [0xBEEF]]))
    assert [t.mosi for t in r.transactions] == [[0xA5A5, 0x1234], [0xBEEF]]


def test_enable_active_low():
    sig = _signals([[0xA5A5]], enable_active_high=False)
    assert decode(*sig, enable_active_high=False).transactions[0].mosi == [0xA5A5]
    # Read with the default active-high gate, the asserted window is the gap
    # between intervals, which carries no clock edges.
    r = decode(*sig)
    assert all(t.mosi == [] for t in r.transactions)


def test_bits_and_bit_order_options():
    assert decode(*_signals([[0x9F, 0xA5]], bits=8), bits=8).transactions[0].mosi == [0x9F, 0xA5]
    sig = _signals([[0x1234]], msb_first=False)
    assert decode(*sig, msb_first=False).transactions[0].mosi == [0x1234]
    assert decode(*sig).transactions[0].mosi == [0x2C48]  # bit-reversed


def test_enable_asserted_at_begin_time():
    # Enable already high at begin_time: the interval opens at the span start.
    clk = DigitalExport(1, [DigitalChunk(0, 0.0, 40.0, array.array("d", [10.0, 12.0]), 1e6)])
    data = DigitalExport(1, [DigitalChunk(1, 0.0, 40.0, array.array("d", []), 1e6)])
    enable = DigitalExport(1, [DigitalChunk(1, 0.0, 40.0, array.array("d", [20.0]), 1e6)])
    r = decode(clk, data, enable, bits=1)
    assert r.truncated == 0
    assert [t.mosi for t in r.transactions] == [[1]]
    assert r.transactions[0].start_s == 0.0


def test_interval_without_clock_edges_is_empty():
    r = decode(*_signals([[]]))
    assert r.transactions[0].mosi == [] and r.leftover_bits == 0 and r.truncated == 0


def test_bad_edge_and_bits_rejected():
    sig = _signals([[0xA5A5]])
    with pytest.raises(ValueError, match="edge must be rising or falling"):
        decode(*sig, edge="both")
    with pytest.raises(ValueError, match="bits must be"):
        decode(*sig, bits=0)


def test_cli_expect_pass_fail_and_bad_argument(tmp_path):
    d = _write(tmp_path, _signals([[0xA5A5, 0x1234]]))
    base = ["syncserial", str(d), "--channels", "12,11,10"]
    assert main([*base, "--expect", "a5a5,1234"]) == 0
    assert main([*base, "--expect", "a5a5,1235"]) == 1
    assert main([*base, "--expect", "zz"]) == 2
    assert main([*base, "--expect", ""]) == 0  # empty string means no --expect
    # A word that does not fit --bits is a bad argument, not a mismatch.
    assert main([*base, "--bits", "8", "--expect", "1234"]) == 2


def test_cli_three_files_json(tmp_path):
    d = _write(tmp_path, _signals([[0xA5A5, 0x1234]]))
    files = [str(d / f"digital_{n}.bin") for n in CHANNELS]
    assert main(["syncserial", *files, "--json", "--expect", "a5a5,1234"]) == 0


def test_cli_json_names_words_not_mosi(tmp_path, capsys):
    d = _write(tmp_path, _signals([[0xA5A5, 0x1234]]))
    assert main(["syncserial", str(d), "--channels", "12,11,10", "--json"]) == 0
    out = capsys.readouterr().out
    assert '"interval_count": 1' in out
    assert '"words"' in out and "mosi" not in out and "miso" not in out


def test_cli_text_report(tmp_path, capsys):
    d = _write(tmp_path, _signals([[0xA5A5]]))
    base = ["syncserial", str(d), "--channels", "12,11,10"]
    assert main([*base, "--expect", "a5a5"]) == 0
    out = capsys.readouterr().out
    assert "1 intervals, 0 leftover bits, 0 truncated" in out
    assert "expect: matched from word 0" in out
    assert main([*base, "--expect", "1234"]) == 1
    assert "expect: pattern not found" in capsys.readouterr().out
    # A pattern that occurs and then diverges reports the offset it broke at.
    d2 = tmp_path / "two"
    d2.mkdir()
    _write(d2, _signals([[0xA5A5, 0x1234], [0xA5A5, 0x9999]]))
    assert main(["syncserial", str(d2), "--channels", "12,11,10", "--expect", "a5a5,1234"]) == 1
    assert "expect: first mismatch at word offset 3" in capsys.readouterr().out


def test_cli_fails_on_truncated_and_leftover(tmp_path):
    cut = tmp_path / "cut"
    cut.mkdir()
    _write(cut, _signals([[0xA5A5]], cut=True))
    assert main(["syncserial", str(cut), "--channels", "12,11,10"]) == 1
    left = tmp_path / "left"
    left.mkdir()
    _write(left, _signals([[0xA5A5, 0xFFFF]], drop_last_bits=5))
    assert main(["syncserial", str(left), "--channels", "12,11,10", "--expect", "a5a5"]) == 1


def test_cli_edge_and_enable_active_low_flags(tmp_path):
    d = tmp_path / "falling"
    d.mkdir()
    _write(d, _signals([[0xBEEF]], edge="falling"))
    base = ["syncserial", str(d), "--channels", "12,11,10"]
    assert main([*base, "--edge", "falling", "--expect", "beef"]) == 0
    assert main([*base, "--expect", "beef"]) == 1
    low = tmp_path / "low"
    low.mkdir()
    _write(low, _signals([[0xA5A5]], enable_active_high=False))
    base_low = ["syncserial", str(low), "--channels", "12,11,10"]
    assert main([*base_low, "--enable-active-low", "--expect", "a5a5"]) == 0
    assert main([*base_low, "--expect", "a5a5"]) == 1


def test_cli_lsb_first(tmp_path):
    d = _write(tmp_path, _signals([[0x1234]], msb_first=False))
    base = ["syncserial", str(d), "--channels", "12,11,10"]
    assert main([*base, "--lsb-first", "--expect", "1234"]) == 0
    assert main([*base, "--expect", "1234"]) == 1


def test_cli_bad_file_counts(tmp_path, capsys):
    d = _write(tmp_path, _signals([[0xA5A5]]))
    assert main(["syncserial", str(d), "--channels", "12,11"]) == 2
    assert "three channel numbers" in capsys.readouterr().err
    assert main(["syncserial", str(d / "digital_12.bin")]) == 2
    assert "three files" in capsys.readouterr().err
    assert main(["syncserial", str(d / "nope.bin"), str(d), str(d)]) == 2
