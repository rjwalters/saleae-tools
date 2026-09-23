"""Portable bench profiles. Parsing and validation require only the stdlib."""

from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def parse_channels(value: str) -> list[int]:
    """Expand ``0-3,7`` while preserving the user's channel/name order."""
    channels: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not re.fullmatch(r"\d+(?:-\d+)?", item):
            raise ValueError("channels must be comma-separated numbers or ranges, e.g. 0-3,7")
        ends = [int(n) for n in item.split("-")]
        first, last = ends[0], ends[-1]
        if not 0 <= first <= last <= 15:
            raise ValueError("digital channels must be in 0..15, with ascending ranges")
        channels.extend(range(first, last + 1))
    if len(set(channels)) != len(channels):
        raise ValueError("digital channels must not repeat")
    return channels


@dataclass
class Analyzer:
    name: str
    label: str
    settings: dict[str, str | int | float | bool]


@dataclass
class Trigger:
    signal: str
    edge: str = "rising"
    pre_trigger_s: float = 0.01
    post_trigger_s: float = 0.05
    timeout_s: float = 30.0

    def validate(self, signals: dict[str, int]) -> None:
        if not isinstance(self.signal, str) or self.signal not in signals:
            raise ValueError("trigger signal must name an enabled signal")
        if self.edge not in ("rising", "falling"):
            raise ValueError("trigger edge must be rising or falling")
        for name in ("pre_trigger_s", "post_trigger_s", "timeout_s"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.post_trigger_s <= 0 or self.timeout_s <= self.post_trigger_s:
            raise ValueError("require timeout_s > post_trigger_s > 0")
        if not math.isfinite(self.pre_trigger_s + self.post_trigger_s):
            raise ValueError("total trigger window must be finite")


@dataclass
class Profile:
    name: str = "capture"
    signals: dict[str, int] = field(default_factory=lambda: {f"digital_{i}": i for i in range(4)})
    sample_rate: int = 100_000_000
    duration_s: float = 1.0
    threshold_v: float = 3.3
    analyzers: list[Analyzer] = field(default_factory=list)
    trigger: Trigger | None = None

    @property
    def channels(self) -> list[int]:
        return sorted(self.signals.values())

    @property
    def signal_names(self) -> list[str]:
        return sorted(self.signals, key=lambda name: self.signals[name])

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("profile name must be a nonempty string")
        if not self.signals:
            raise ValueError("at least one signal is required")
        for name, channel in self.signals.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError(
                    f"invalid signal name {name!r}; use letters, digits and underscores"
                )
            if type(channel) is not int or not 0 <= channel <= 15:
                raise ValueError(f"signal {name!r}: channel must be an integer in 0..15")
        if len(set(self.signals.values())) != len(self.signals):
            raise ValueError("signals must have distinct channels")
        if type(self.sample_rate) is not int or self.sample_rate <= 0:
            raise ValueError("sample_rate must be a positive integer (samples/s)")
        if (
            type(self.duration_s) not in (int, float)
            or not math.isfinite(self.duration_s)
            or self.duration_s <= 0
        ):
            raise ValueError("duration_s must be finite and positive")
        if type(self.threshold_v) not in (int, float) or self.threshold_v not in (1.2, 1.8, 3.3):
            raise ValueError("threshold_v must be a Logic Pro preset: 1.2, 1.8 or 3.3")
        labels = [a.label for a in self.analyzers]
        if len(set(labels)) != len(labels):
            raise ValueError("analyzer labels must be unique")
        if self.trigger is not None:
            self.trigger.validate(self.signals)


def _table(value: Any, context: str, allowed: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a table")
    if allowed is not None and (unknown := value.keys() - allowed):
        raise ValueError(f"unknown {context} field(s): {', '.join(sorted(unknown))}")
    return dict(value)


def load_profile(path: str | Path) -> Profile:
    with open(path, "rb") as stream:
        doc = _table(
            tomllib.load(stream),
            "profile",
            {"version", "name", "signals", "capture", "analyzers", "trigger"},
        )
    if type(doc.get("version")) is not int or doc["version"] != 1:
        raise ValueError("profile version must be 1")
    capture = _table(
        doc.get("capture", {}), "capture", {"sample_rate", "duration_s", "threshold_v"}
    )
    profile = Profile(
        name=doc.get("name", Path(path).stem),
        signals=_table(doc.get("signals", {}), "signals"),
        **capture,
    )
    if "trigger" in doc:
        trigger = _table(
            doc["trigger"],
            "trigger",
            {"signal", "edge", "pre_trigger_s", "post_trigger_s", "timeout_s"},
        )
        if "signal" not in trigger:
            raise ValueError("trigger.signal is required")
        profile.trigger = Trigger(**trigger)
    profile.validate()
    analyzers = doc.get("analyzers", [])
    if not isinstance(analyzers, list):
        raise ValueError("analyzers must be an array of tables ([[analyzers]])")
    for entry in analyzers:
        entry = _table(entry, "analyzer", {"name", "label", "channels", "settings"})
        name = entry.get("name")
        label = entry.get("label", name)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("analyzer name must be a nonempty string")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("analyzer label must be a nonempty string")
        settings = _table(entry.get("settings", {}), "analyzer settings")
        for key, value in settings.items():
            if type(value) not in (str, int, float, bool) or (
                isinstance(value, float) and not math.isfinite(value)
            ):
                raise ValueError(f"analyzer setting {key!r} must be a finite scalar")
        # Separate channel references from literal dropdown values/bit rates.
        for key, signal in _table(entry.get("channels", {}), "analyzer channels").items():
            if key in settings:
                raise ValueError(f"analyzer setting {key!r} is also listed in channels")
            if not isinstance(signal, str) or signal not in profile.signals:
                raise ValueError(f"analyzer channel {key!r} references unknown signal {signal!r}")
            settings[key] = profile.signals[signal]
        profile.analyzers.append(Analyzer(name, label, settings))
    profile.validate()
    return profile
