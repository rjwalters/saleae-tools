import array
import io

import pytest

from saleae_tools import binexport as be
from saleae_tools.vcd import _id_code, write_vcd


def _chunk(initial, begin, end, trans, rate=None):
    return be.DigitalChunk(initial, begin, end, array.array("d", trans), rate)


def test_id_codes_unique_and_printable():
    codes = [_id_code(i) for i in range(300)]
    assert len(set(codes)) == 300
    assert all(all(33 <= ord(ch) <= 126 for ch in c) for c in codes)
    assert _id_code(0) == "!" and _id_code(94) == "!!"


def test_two_channels_merge():
    clk = be.DigitalExport(0, [_chunk(0, 0.0, 40e-9, [10e-9, 20e-9, 30e-9])])
    dat = be.DigitalExport(0, [_chunk(1, 0.0, 40e-9, [20e-9])])
    buf = io.StringIO()
    n = write_vcd(buf, [clk, dat], ["clk", "dat"])
    text = buf.getvalue()
    assert "$timescale 1ns $end" in text
    assert "$var wire 1 ! clk $end" in text
    assert '$var wire 1 " dat $end' in text
    body = text.split("$enddefinitions $end\n", 1)[1]
    assert body == ('#0\n0!\n1"\n#10\n1!\n#20\n0!\n0"\n#30\n1!\n#40\nx!\nx"\n')
    assert n == 10


def test_chunk_gap_renders_x():
    e = be.DigitalExport(1, [_chunk(0, 0.0, 1e-9, [], 1e9), _chunk(1, 5e-9, 6e-9, [], 1e9)])
    buf = io.StringIO()
    write_vcd(buf, [e], ["a"])
    body = buf.getvalue().split("$enddefinitions $end\n", 1)[1]
    assert body == "#0\n0!\n#1\nx!\n#5\n1!\n#6\nx!\n"


def test_origin_defaults_to_earliest_begin():
    a = be.DigitalExport(0, [_chunk(0, 1.0, 1.0 + 1e-9, [])])
    b = be.DigitalExport(0, [_chunk(1, 1.0 + 2e-9, 1.0 + 3e-9, [])])
    buf = io.StringIO()
    write_vcd(buf, [a, b])
    body = buf.getvalue().split("$enddefinitions $end\n", 1)[1]
    assert body.startswith('#0\n0!\n#1\nx!\n#2\n1"\n')


def test_bad_args():
    e = be.DigitalExport(0, [_chunk(0, 0.0, 1e-9, [])])
    with pytest.raises(ValueError):
        write_vcd(io.StringIO(), [e], ["a", "b"])
    with pytest.raises(ValueError):
        write_vcd(io.StringIO(), [e], timescale="1fs")


def test_write_to_path(tmp_path):
    e = be.DigitalExport(0, [_chunk(0, 0.0, 1e-9, [])])
    out = tmp_path / "x.vcd"
    write_vcd(out, [e], ["a"], timescale="1ps")
    assert out.read_text().count("$timescale 1ps $end") == 1
