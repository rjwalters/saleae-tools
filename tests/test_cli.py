import array
import json

from saleae_tools import binexport as be
from saleae_tools.cli import main


def _write(tmp_path, name, initial=0):
    p = tmp_path / name
    be.write_digital(
        p,
        be.DigitalExport(
            0, [be.DigitalChunk(initial, 0.0, 1e-6, array.array("d", [2e-7, 4e-7, 6e-7]))]
        ),
    )
    return p


def test_info_json(tmp_path, capsys):
    p = _write(tmp_path, "digital_0.bin")
    assert main(["info", "--json", str(p)]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["kind"] == "digital"
    assert rows[0]["num_transitions"] == 3


def test_info_text_and_analog(tmp_path, capsys):
    p = _write(tmp_path, "digital_0.bin")
    a = tmp_path / "analog_0.bin"
    be.write_analog(
        a, be.AnalogExport(0, [be.AnalogWaveform(0.0, 1e6, 1, array.array("f", [1.0]))])
    )
    assert main(["info", str(p), str(a)]) == 0
    out = capsys.readouterr().out
    assert "digital v0" in out and "analog v0" in out


def test_vcd_orders_by_channel(tmp_path, capsys):
    p10 = _write(tmp_path, "digital_10.bin", 1)
    p2 = _write(tmp_path, "digital_2.bin", 0)
    out = tmp_path / "o.vcd"
    assert main(["vcd", str(p10), str(p2), "-o", str(out)]) == 0
    text = out.read_text()
    assert text.index("digital_2") < text.index("digital_10")


def test_vcd_names_mismatch(tmp_path):
    p = _write(tmp_path, "digital_0.bin")
    assert main(["vcd", str(p), "-o", str(tmp_path / "o.vcd"), "--names", "a,b"]) == 2


def test_dump_limit(tmp_path, capsys):
    p = _write(tmp_path, "digital_0.bin")
    assert main(["dump", str(p), "-n", "2"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_bad_file(tmp_path, capsys):
    p = tmp_path / "junk.bin"
    p.write_bytes(b"x" * 16)
    assert main(["info", str(p)]) == 1
    assert "error:" in capsys.readouterr().err
