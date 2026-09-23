"""Edge measurements on exported data, independent of Logic 2 or a decoder."""

from __future__ import annotations

from dataclasses import dataclass

from saleae_tools.binexport import DigitalExport


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
