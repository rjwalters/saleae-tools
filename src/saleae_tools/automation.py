"""Thin wrapper over Saleae's ``logic2-automation`` gRPC client.

Requires the ``automation`` extra. Everything here imports the Saleae package
lazily so the rest of ``saleae_tools`` stays importable without it.

Two ways to reach a server:

* ``connect()`` - attach to a Logic 2 that already has *Settings > Automation
  > Automation server* enabled (default port 10430).
* ``launch()`` - start one. With ``headless=True`` this uses the native
  headless server that shipped as a preview with ``logic2_automation`` 1.1.0
  (2026-08-08). Older clients reject the keyword; we fall back to the GUI
  launch and say so.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PORT = 10430


class AutomationUnavailable(RuntimeError):
    """The ``logic2-automation`` package is not installed."""


def _api() -> Any:
    try:
        from saleae import automation
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise AutomationUnavailable(
            "logic2-automation is not installed; `uv sync --extra automation` "
            "or `pip install 'saleae-tools[automation]'`"
        ) from e
    return automation


@dataclass(frozen=True)
class Device:
    device_id: str
    device_type: str
    is_simulation: bool


@contextmanager
def connect(port: int = DEFAULT_PORT, address: str = "127.0.0.1") -> Iterator[Any]:
    """Attach to a running Logic 2 automation server."""
    automation = _api()
    with automation.Manager.connect(address=address, port=port) as manager:
        yield manager


@contextmanager
def launch(headless: bool = False, port: int | None = None) -> Iterator[Any]:
    """Launch Logic 2 (or the native headless server) and yield the manager."""
    automation = _api()
    kwargs: dict[str, Any] = {}
    if port is not None:
        kwargs["port"] = port
    if headless:
        try:
            cm = automation.Manager.launch(headless=True, **kwargs)
        except TypeError:
            raise AutomationUnavailable(
                "this logic2-automation build has no headless=True; install the 1.1.0 "
                "preview wheel (see docs/survey.md) or launch the GUI instead"
            ) from None
    else:
        cm = automation.Manager.launch(**kwargs)
    with cm as manager:
        yield manager


def list_devices(manager: Any, include_simulation: bool = False) -> list[Device]:
    return [
        Device(d.device_id, str(d.device_type), bool(d.is_simulation))
        for d in manager.get_devices(include_simulation_devices=include_simulation)
    ]


def capture_timed(
    manager: Any,
    *,
    device_id: str | None,
    digital_channels: Sequence[int],
    sample_rate: int,
    duration_s: float,
    threshold_v: float = 3.3,
    analog_channels: Sequence[int] = (),
    analog_sample_rate: int | None = None,
) -> Any:
    """Run a timed capture and return the finished ``Capture``.

    ``threshold_v`` is the digital logic threshold; 3.3 suits ECP5 I/O.
    """
    automation = _api()
    cfg = automation.LogicDeviceConfiguration(
        enabled_digital_channels=list(digital_channels),
        digital_sample_rate=sample_rate,
        digital_threshold_volts=threshold_v,
        enabled_analog_channels=list(analog_channels),
        analog_sample_rate=analog_sample_rate,
    )
    cap_cfg = automation.CaptureConfiguration(
        capture_mode=automation.TimedCaptureMode(duration_seconds=duration_s)
    )
    capture = manager.start_capture(
        device_id=device_id, device_configuration=cfg, capture_configuration=cap_cfg
    )
    capture.wait()
    return capture


def export_binary(
    capture: Any,
    directory: str | Path,
    digital_channels: Sequence[int] | None = None,
    analog_channels: Sequence[int] | None = None,
) -> Path:
    """Export raw channel data as ``digital_<n>.bin`` / ``analog_<n>.bin``."""
    # Logic 2 resolves relative paths against ITS cwd (a read-only disk image
    # when the app runs translocated), so always hand it an absolute path.
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    capture.export_raw_data_binary(
        directory=str(directory),
        digital_channels=list(digital_channels) if digital_channels is not None else None,
        analog_channels=list(analog_channels) if analog_channels is not None else None,
    )
    return directory
