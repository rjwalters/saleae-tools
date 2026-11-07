import array
from pathlib import Path

import pytest

from saleae_tools.binexport import DigitalChunk, DigitalExport, write_digital
from saleae_tools.cli import main
from saleae_tools.spi import decode

SLOT = 4.0  # time units per bit


def _bits(word, bits, msb_first):
    order = range(bits - 1, -1, -1) if msb_first else range(bits)
    return [(word >> k) & 1 for k in order]


def _signals(txns, *, mode=0, bits=8, msb_first=True, drop_last_bits=0, cut=False):
    """Build (sclk, mosi, miso, cs_n) exports; txns is a list of (mosi, miso) word lists.

    Per bit slot: CPHA=0 sets data at +0, leading edge +1, trailing edge +3;
    CPHA=1 has leading edge +1, sets data at +2, trailing edge +3.
    """
    cpol, cpha = (1 if mode >= 2 else 0), mode & 1
    trans: dict[str, list[float]] = {"sclk": [], "mosi": [], "miso": [], "cs": []}
    level = {"sclk": cpol, "mosi": 0, "miso": 0, "cs": 1}

    def set_(name, lvl, at):
        if level[name] != lvl:
            trans[name].append(at)
            level[name] = lvl

    t = 10.0
    for mo, mi in txns:
        set_("cs", 0, t)
        mbits = [b for w in mo for b in _bits(w, bits, msb_first)]
        ibits = [b for w in mi for b in _bits(w, bits, msb_first)]
        if drop_last_bits:
            mbits, ibits = mbits[:-drop_last_bits], ibits[:-drop_last_bits]
        t += SLOT
        for mb, ib in zip(mbits, ibits, strict=True):
            at = t + (2 if cpha else 0)
            set_("mosi", mb, at)
            set_("miso", ib, at)
            set_("sclk", 1 - cpol, t + 1)
            set_("sclk", cpol, t + 3)
            t += SLOT
        t += SLOT
        if cut:
            break
        set_("cs", 1, t)
        t += 3 * SLOT
    end = t + SLOT

    def ch(init, name):
        return DigitalExport(1, [DigitalChunk(init, 0.0, end, array.array("d", trans[name]), 1e6)])

    return ch(cpol, "sclk"), ch(0, "mosi"), ch(0, "miso"), ch(1, "cs")


def _write(tmp_path: Path, sig, with_miso=True):
    for i, e in enumerate(sig):
        if i == 2 and not with_miso:
            continue
        write_digital(tmp_path / f"digital_{i}.bin", e)
    return tmp_path


@pytest.mark.parametrize("mode", [0, 1, 2, 3])
def test_modes(mode):
    sig = _signals([([0x9F, 0x00, 0xA5], [0x12, 0x34, 0xFF])], mode=mode)
    r = decode(*sig, mode=mode)
    assert r.truncated == 0 and r.leftover_bits == 0
    assert [t.mosi for t in r.transactions] == [[0x9F, 0x00, 0xA5]]
    assert [t.miso for t in r.transactions] == [[0x12, 0x34, 0xFF]]


def test_wrong_mode_differs():
    sig = _signals([([0x9F], [0x00])], mode=1)
    assert decode(*sig, mode=0).transactions[0].mosi != [0x9F]


def test_multiple_transactions_and_lsb_first():
    sig = _signals([([0x01, 0x80], [0, 0]), ([0xAA], [0x55])], msb_first=False)
    r = decode(*sig, msb_first=False)
    assert [t.mosi for t in r.transactions] == [[0x01, 0x80], [0xAA]]
    assert r.transactions[1].miso == [0x55]


def test_bits_16():
    sig = _signals([([0xBEEF], [0x1234])], bits=16)
    assert decode(*sig, bits=16).transactions[0].mosi == [0xBEEF]


def test_leftover_bits():
    sig = _signals([([0x9F, 0xFF], [0, 0])], drop_last_bits=3)
    r = decode(*sig)
    assert r.transactions[0].mosi == [0x9F]
    assert r.leftover_bits == 5


def test_truncated_by_chunk_end():
    r = decode(*_signals([([0x9F], [0x00])], cut=True))
    assert r.truncated == 1 and r.transactions == []


def test_missing_miso():
    sig = _signals([([0x9F], [0x00])])
    r = decode(sig[0], sig[1], None, sig[3])
    assert r.transactions[0].miso is None


def test_cs_glitch_without_clock_is_empty():
    r = decode(*_signals([([], [])]))
    assert r.transactions[0].mosi == [] and r.leftover_bits == 0


def test_bad_mode_and_chunk_mismatch():
    sig = _signals([([1], [1])])
    with pytest.raises(ValueError):
        decode(*sig, mode=4)
    sig[1].chunks.append(sig[1].chunks[0])
    with pytest.raises(ValueError):
        decode(*sig)


def test_cli_expect_pass_and_fail(tmp_path):
    d = _write(tmp_path, _signals([([0x9F, 0x00, 0x00], [0, 0x11, 0x22])]))
    base = ["spi", str(d), "--channels", "0,1,2,3"]
    assert main([*base, "--expect", "9f,00,00"]) == 0
    assert main([*base, "--expect", "9f,00,01"]) == 1
    assert main([*base, "--expect-miso", "00,11,22"]) == 0
    assert main([*base, "--expect", "zz"]) == 2


def test_cli_four_files_json(tmp_path, capsys):
    d = _write(tmp_path, _signals([([0x9F], [0x00])]))
    files = [str(d / f"digital_{i}.bin") for i in range(4)]
    assert main(["spi", *files, "--json", "--expect", "9f"]) == 0
    assert '"transaction_count": 1' in capsys.readouterr().out


def test_cli_fails_on_truncated_and_leftover(tmp_path):
    d = tmp_path / "t"
    d.mkdir()
    _write(d, _signals([([0x9F], [0x00])], cut=True))
    assert main(["spi", str(d), "--channels", "0,1,2,3"]) == 1
    d2 = tmp_path / "l"
    d2.mkdir()
    _write(d2, _signals([([0x9F, 0xFF], [0, 0])], drop_last_bits=3))
    assert main(["spi", str(d2), "--channels", "0,1,2,3", "--expect", "9f"]) == 1


def test_cli_missing_miso(tmp_path):
    d = _write(tmp_path, _signals([([0x9F], [0x00])]), with_miso=False)
    assert main(["spi", str(d), "--channels", "0,1,2,3"]) == 0
    assert main(["spi", str(d), "--channels", "0,1,2,3", "--expect-miso", "00"]) == 2
