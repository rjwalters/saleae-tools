import array

import pytest

from saleae_tools.binexport import DigitalChunk, DigitalExport, read_digital, write_digital
from saleae_tools.timing import BOUNDED, check_bounds, measure, validate_bounds


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


def _measured(tmp_path):
    """high_pulse 2x2us, low_pulse 1x2us, rising/falling_period 1x4us."""
    path = tmp_path / "digital_0.bin"
    write_digital(
        path,
        DigitalExport(0, [DigitalChunk(0, 0, 10e-6, array.array("d", [1e-6, 3e-6, 5e-6, 7e-6]))]),
    )
    return measure(read_digital(path))


def test_check_bounds_without_bounds_reports_nothing(tmp_path):
    assert check_bounds(_measured(tmp_path), {}) == []


def test_check_bounds_satisfied_min_and_max(tmp_path):
    bounds = {"min_high_pulse": 1e-6, "max_high_pulse": 3e-6, "max_rising_period": 5e-6}
    assert check_bounds(_measured(tmp_path), bounds) == []


def test_check_bounds_violated_minimum(tmp_path):
    violations = check_bounds(_measured(tmp_path), {"min_low_pulse": 3e-6})
    assert violations == [
        {
            "distribution": "low_pulse",
            "bound": "min",
            "limit_s": 3e-6,
            "observed_s": pytest.approx(2e-6),
        }
    ]


def test_check_bounds_violated_maximum(tmp_path):
    violations = check_bounds(_measured(tmp_path), {"max_falling_period": 1e-6})
    assert violations == [
        {
            "distribution": "falling_period",
            "bound": "max",
            "limit_s": 1e-6,
            "observed_s": pytest.approx(4e-6),
        }
    ]


@pytest.mark.parametrize("side", ["min", "max"])
def test_check_bounds_empty_distribution_violates_either_bound(side):
    """An absence of measurements is not a passing timing check (docs/bringup.md)."""
    result = measure(DigitalExport(1))
    violations = check_bounds(result, {f"{side}_high_pulse": 1e-6})
    assert violations == [
        {
            "distribution": "high_pulse",
            "bound": side,
            "limit_s": 1e-6,
            "observed_s": None,
        }
    ]


def test_check_bounds_equal_limit_passes_and_order_is_fixed(tmp_path):
    result = _measured(tmp_path)
    bounds = {f"{side}_{key}": 0.0 for key in reversed(BOUNDED) for side in ("max", "min")}
    bounds.update({f"min_{key}": 1.0 for key in BOUNDED})
    assert [(v["distribution"], v["bound"]) for v in check_bounds(result, bounds)] == [
        (key, side) for key in BOUNDED for side in ("min", "max")
    ]
    # A limit exactly equal to the observed value is satisfied, not violated.
    # (Taken from the result: 3e-6 - 1e-6 is not exactly 2e-6 in binary floats.)
    low = result["low_pulse"]
    exact = {"min_low_pulse": low["min_s"], "max_low_pulse": low["max_s"]}
    assert low["min_s"] == low["max_s"]
    assert check_bounds(result, exact) == []


@pytest.mark.parametrize(
    "bounds",
    [
        {"min_high_pulse": float("nan")},
        {"max_high_pulse": float("inf")},
        {"min_low_pulse": -1e-6},
        {"min_rising_period": 2e-6, "max_rising_period": 1e-6},
    ],
)
def test_validate_bounds_rejects_unsatisfiable_bounds(bounds):
    with pytest.raises(ValueError):
        validate_bounds(bounds)


def test_validate_bounds_accepts_zero_minimum_and_equal_limits():
    validate_bounds({})
    validate_bounds({"min_high_pulse": 0.0, "max_high_pulse": 0.0})
