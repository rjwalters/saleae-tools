"""Edge measurements on exported data, independent of Logic 2 or a decoder."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from saleae_tools.binexport import DigitalExport

#: The ``measure`` keys a min/max bound can be set on, in report order.
BOUNDED = ("high_pulse", "low_pulse", "rising_period", "falling_period")


@dataclass
class Distribution:
    count: int = 0
    min_s: float | None = None
    max_s: float | None = None
    mean_s: float | None = None

    def add(self, value: float) -> None:
        self.count += 1
        self.min_s = value if self.min_s is None else min(self.min_s, value)
        self.max_s = value if self.max_s is None else max(self.max_s, value)
        self.mean_s = (
            value if self.mean_s is None else self.mean_s + (value - self.mean_s) / self.count
        )


def measure(export: DigitalExport) -> dict[str, object]:
    """Measure complete pulses and like-edge periods within each chunk.

    Neither boundary-truncated levels nor gaps between chunks are pulses.
    Periods include idle time inside a chunk; they are not a baud estimate.
    """
    from dataclasses import asdict

    high, low, rising, falling = (Distribution() for _ in range(4))
    rising_edges = falling_edges = 0
    for chunk in export.chunks:
        state = chunk.initial_state
        previous: float | None = None
        last_rising: float | None = None
        last_falling: float | None = None
        for time in chunk.transitions:
            if previous is not None:
                (high if state else low).add(time - previous)
            state ^= 1
            if state:
                rising_edges += 1
                if last_rising is not None:
                    rising.add(time - last_rising)
                last_rising = time
            else:
                falling_edges += 1
                if last_falling is not None:
                    falling.add(time - last_falling)
                last_falling = time
            previous = time
    return {
        "chunks": len(export.chunks),
        "observed_duration_s": sum(c.end_time - c.begin_time for c in export.chunks),
        "rising_edges": rising_edges,
        "falling_edges": falling_edges,
        "high_pulse": asdict(high),
        "low_pulse": asdict(low),
        "rising_period": asdict(rising),
        "falling_period": asdict(falling),
    }


def validate_bounds(bounds: Mapping[str, float]) -> None:
    """Reject bounds that no capture could satisfy, before any file is read.

    Keys are ``min_<key>``/``max_<key>`` over :data:`BOUNDED`. ``argparse``
    accepts ``nan``, ``inf`` and negative seconds through ``type=float``;
    none of them describe a pulse width. ``min == max`` and a ``0`` minimum
    are legal. Raises ``ValueError``, which the CLI turns into exit 2.
    """
    for name, limit in bounds.items():
        flag = "--" + name.replace("_", "-")
        if not math.isfinite(limit):
            raise ValueError(f"{flag} must be a finite number of seconds")
        if limit < 0:
            raise ValueError(f"{flag} must not be negative")
    for key in BOUNDED:
        low, high = bounds.get(f"min_{key}"), bounds.get(f"max_{key}")
        if low is not None and high is not None and low > high:
            flag = key.replace("_", "-")
            raise ValueError(f"--min-{flag} must not exceed --max-{flag}")


def check_bounds(row: Mapping[str, object], bounds: Mapping[str, float]) -> list[dict[str, object]]:
    """Compare a :func:`measure` result against min/max bounds, in seconds.

    Returns one record per violated bound, in :data:`BOUNDED` order with
    ``min`` before ``max``; an empty list means every bound given passed.
    A ``min`` bound is violated when ``min_s`` is below it and a ``max``
    bound when ``max_s`` is above it. A distribution with ``count`` 0
    violates **either** bound, with ``observed_s`` null: no measurement is
    an absence of evidence, not a passing timing check.
    """
    violations: list[dict[str, object]] = []
    for key in BOUNDED:
        measured = row.get(key)
        stats: dict[str, object] = measured if isinstance(measured, dict) else {}
        empty = stats.get("count") == 0
        for side, stat in (("min", "min_s"), ("max", "max_s")):
            limit = bounds.get(f"{side}_{key}")
            if limit is None:
                continue
            observed = stats.get(stat)
            value = float(observed) if isinstance(observed, int | float) else None
            if empty or value is None:
                violated, value = True, None
            else:
                violated = value < limit if side == "min" else value > limit
            if violated:
                violations.append(
                    {
                        "distribution": key,
                        "bound": side,
                        "limit_s": limit,
                        "observed_s": value,
                    }
                )
    return violations
