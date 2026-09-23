import array
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_capture_dry_run_orders_named_channels(capsys):
    assert (
        main(
            [
                "capture",
                "--dry-run",
                "--channels",
                "10,2-3",
                "--names",
                "cs_n,sclk,mosi",
                "--seconds",
                "0.01",
            ]
        )
        == 0
    )
    profile = json.loads(capsys.readouterr().out)
    assert profile["signals"] == {"cs_n": 10, "sclk": 2, "mosi": 3}
    assert profile["duration_s"] == 0.01


def test_profile_overrides(capsys):
    path = Path(__file__).parents[1] / "examples/icepi-uart.toml"
    assert main(["capture", "--dry-run", "--profile", str(path), "--seconds", "2"]) == 0
    profile = json.loads(capsys.readouterr().out)
    assert profile["duration_s"] == 2
    assert profile["analyzers"][0]["settings"]["Input Channel"] == 6


@pytest.mark.parametrize(
    "args",
    [
        ["--channels", "0,0"],
        ["--seconds", "nan"],
        ["--seconds", "-1"],
        ["--rate", "0"],
        ["--names", "one"],
        ["--threshold", "5"],
        ["--trigger", "missing"],
        ["--post", "0.2"],
        ["--trigger", "digital_0", "--seconds", "1"],
        ["--trigger", "digital_0", "--timeout", "0.01"],
        ["--profile", "examples/icepi-spi.toml", "--channels", "1,2"],
    ],
)
def test_capture_invalid_options(args, capsys):
    assert main(["capture", "--dry-run", *args]) == 1
    assert "error:" in capsys.readouterr().err


def test_offline_profile_needs_no_installed_packages():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import sys; sys.path.insert(0, 'src'); from saleae_tools.cli import main; "
            "raise SystemExit(main(['capture', '--profile', 'examples/icepi-spi.toml', '--dry-run']))",
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["analyzers"][0]["name"] == "SPI"


def test_timing_json(tmp_path, capsys):
    path = _write(tmp_path, "digital_0.bin")
    assert main(["timing", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)[0]
    assert result["high_pulse"]["count"] == 1
    assert result["low_pulse"]["count"] == 1


def test_trigger_override_and_timed_escape(capsys):
    args = ["capture", "--dry-run", "--profile", "examples/icepi-board.toml"]
    assert main([*args, "--trigger", "cs_n", "--edge", "falling", "--post", ".2"]) == 0
    profile = json.loads(capsys.readouterr().out)
    assert profile["trigger"]["signal"] == "cs_n"
    assert profile["trigger"]["edge"] == "falling"
    assert profile["trigger"]["post_trigger_s"] == 0.2
    assert main([*args, "--timed", "--seconds", ".1"]) == 0
    profile = json.loads(capsys.readouterr().out)
    assert profile["trigger"] is None
    assert profile["duration_s"] == 0.1


def test_board_helper_dry_run_does_not_create_results(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/capture-board.py",
            "--dry-run",
            "--protocol",
            "spi",
            "--trigger",
            "cs_n",
            "--edge",
            "falling",
            "--output-root",
            str(tmp_path / "results"),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    profile = json.loads(result.stdout)
    assert profile["signals"]["cs_n"] == 3
    assert profile["trigger"]["edge"] == "falling"
    assert not (tmp_path / "results").exists()
