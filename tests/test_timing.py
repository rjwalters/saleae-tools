import array

import pytest

from saleae_tools.binexport import DigitalChunk, DigitalExport, read_digital, write_digital
from saleae_tools.timing import measure


def test_measure_complete_pulses(tmp_path):
    path = tmp_path / "digital_0.bin"
    write_digital(
        path,
        DigitalExport(0, [DigitalChunk(0, 0, 10e-6, array.array("d", [1e-6, 3e-6, 5e-6, 7e-6]))]),
    )
    result = measure(read_digital(path))
    assert result["rising_edges"] == result["falling_edges"] == 2
    assert result["high_pulse"]["count"] == 2
    assert result["high_pulse"]["min_s"] == pytest.approx(2e-6)
    assert result["low_pulse"]["count"] == 1  # partial levels at the boundaries excluded
    assert result["rising_period"]["mean_s"] == pytest.approx(4e-6)
    assert result["falling_period"]["mean_s"] == pytest.approx(4e-6)


def test_gaps_and_initial_high_do_not_create_pulses(tmp_path):
    path = tmp_path / "digital_0.bin"
    write_digital(
        path,
        DigitalExport(
            1,
            [
                DigitalChunk(1, 0, 5, array.array("d", [1, 3]), 1e6),
                DigitalChunk(1, 10, 15, array.array("d", [11, 14]), 1e6),
            ],
        ),
    )
    result = measure(read_digital(path))
    assert result["observed_duration_s"] == 10
    assert result["high_pulse"]["count"] == 0
    assert result["low_pulse"] == {"count": 2, "min_s": 2, "max_s": 3, "mean_s": 2.5}
    assert result["rising_period"]["count"] == result["falling_period"]["count"] == 0


def test_constant_and_empty_captures():
    for export in (DigitalExport(1), DigitalExport(0, [DigitalChunk(0, 0, 1, array.array("d"))])):
        result = measure(export)
        assert result["rising_edges"] == result["falling_edges"] == 0
        assert result["high_pulse"] == {"count": 0, "min_s": None, "max_s": None, "mean_s": None}
