"""Thin wrapper over Saleae's ``logic2-automation`` gRPC client.

Requires the ``automation`` extra. Everything here imports the Saleae package
lazily so the rest of ``saleae_tools`` stays importable without it.

Two ways to reach a server:

* ``connect()`` - attach to a Logic 2 that already has *Settings > Automation
  > Automation server* enabled (default port 10430).
* ``launch()`` - start one. With ``headless=True`` this uses the native
  headless server that shipped as a preview with ``logic2_automation`` 1.1.0
  (2026-08-08). Older clients reject the keyword with an actionable error.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saleae_tools.profile import Profile

DEFAULT_PORT = 10430


class AutomationError(RuntimeError):
    """An operator-facing Logic 2 connection or capture error."""


class AutomationUnavailable(AutomationError):
    """The ``logic2-automation`` package is not installed."""


class CaptureTimeout(AutomationError):
    """The trigger and its post-trigger recording did not complete in time."""


def _grpc_options() -> list[tuple[str, str]]:
    # Bound setup/cleanup RPCs too, including an unresponsive running GUI.
    # Exports may be large; leave their deadlines to the SDK/server.
    return [
        (
            "grpc.service_config",
            json.dumps(
                {
                    "methodConfig": [
                        {
                            "name": [
                                {"service": "saleae.automation.Manager", "method": method}
                                for method in (
                                    "GetAppInfo",
                                    "GetDevices",
                                    "StartCapture",
                                    "CloseCapture",
                                )
                            ],
                            "timeout": "5s",
                        }
                    ]
                }
            ),
        )
    ]


def _api() -> Any:
    try:
        from saleae import automation
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise AutomationUnavailable(
            "logic2-automation is not installed; `uv sync --extra automation` "
            "or `pip install 'saleae-tools[automation]'`"
        ) from e
    return automation


@contextmanager
def _errors() -> Iterator[None]:
    api = _api()
    import grpc

    try:
        yield
    except grpc.RpcError as exc:
        raise AutomationError(
            f"Logic 2 automation: {exc}. Check Settings > Automation > "
            "automation server (default port 10430)."
        ) from exc
    except api.SaleaeError as exc:
        raise AutomationError(f"Logic 2: {exc}") from exc


@dataclass(frozen=True)
class Device:
    device_id: str
    device_type: str
    is_simulation: bool


@contextmanager
def connect(port: int = DEFAULT_PORT, address: str = "127.0.0.1") -> Iterator[Any]:
    """Attach to a running Logic 2 automation server."""
    automation = _api()
    with (
        _errors(),
        automation.Manager.connect(
            address=address,
            port=port,
            connect_timeout_seconds=5,
            grpc_channel_arguments=_grpc_options(),
        ) as manager,
    ):
        yield manager


@contextmanager
def launch(headless: bool = False, port: int | None = None) -> Iterator[Any]:
    """Launch Logic 2 (or the native headless server) and yield the manager."""
    automation = _api()
    kwargs: dict[str, Any] = {"grpc_channel_arguments": _grpc_options()}
    if port is not None:
        kwargs["port"] = port
    with _errors():
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


def select_device(manager: Any, device_id: str | None = None) -> Device:
    """Select one real device by default; simulations require an explicit ID."""
    devices = list_devices(manager, include_simulation=device_id is not None)
    if device_id is not None:
        devices = [d for d in devices if d.device_id == device_id]
    if not devices:
        raise AutomationError("no matching Saleae device; run `slt devices --json`")
    if len(devices) != 1:
        raise AutomationError("multiple Saleae devices; select one with --device")
    return devices[0]


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

    ``threshold_v`` selects a Logic Pro voltage preset; use 3.3 for a
    verified 3.3 V I/O bank. It is not a literal 3.3 V comparator trip point.
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
    try:
        capture.wait()
    except BaseException:
        # Preserve the wait error, including Ctrl-C, if cleanup also fails.
        with suppress(Exception):
            capture.close()
        raise
    return capture


def _wait_for_trigger(capture: Any, timeout_s: float) -> None:
    """Use the SDK's WaitCapture RPC with a deadline and cancellable future.

    Capture.wait() has no timeout argument in logic2-automation 1.0.11.
    Keep this transport-level compatibility code here, behind lazy imports.
    Never call stop() after this wait: the API prohibits combining them.
    """
    _api()
    import grpc
    from saleae.grpc import saleae_pb2

    pending = capture.manager.stub.WaitCapture.future(
        saleae_pb2.WaitCaptureRequest(capture_id=capture.capture_id), timeout=timeout_s
    )
    try:
        pending.result()
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise CaptureTimeout(
                f"triggered capture did not complete within {timeout_s:g}s "
                "(including post-trigger recording); no successful capture was exported"
            ) from exc
        raise
    finally:
        pending.cancel()


def capture_triggered(
    manager: Any,
    *,
    device_id: str,
    profile: Profile,
    on_started: Callable[[], None] | None = None,
) -> Any:
    """Capture an edge and a bounded window; return only after completion."""
    profile.validate()
    trigger = profile.trigger
    if trigger is None:
        raise ValueError("a trigger is required")
    api = _api()
    capture = manager.start_capture(
        device_id=device_id,
        device_configuration=api.LogicDeviceConfiguration(
            enabled_digital_channels=profile.channels,
            digital_sample_rate=profile.sample_rate,
            digital_threshold_volts=profile.threshold_v,
        ),
        capture_configuration=api.CaptureConfiguration(
            buffer_size_megabytes=256,
            capture_mode=api.DigitalTriggerCaptureMode(
                trigger_type=getattr(api.DigitalTriggerType, trigger.edge.upper()),
                trigger_channel_index=profile.signals[trigger.signal],
                after_trigger_seconds=trigger.post_trigger_s,
                trim_data_seconds=trigger.pre_trigger_s + trigger.post_trigger_s,
            ),
        ),
    )
    try:
        if on_started is not None:
            on_started()
        _wait_for_trigger(capture, trigger.timeout_s)
    except BaseException as exc:
        try:
            capture.close()
        except Exception as cleanup:
            exc.add_note(f"Capture cleanup failed; check Logic 2: {cleanup}")
        raise
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


def export_analyzers(capture: Any, directory: str | Path, profile: Profile) -> Path | None:
    """Decode with Logic 2's analyzers and export their data table."""
    if not profile.analyzers:
        return None
    handles = [
        capture.add_analyzer(a.name, label=a.label, settings=a.settings) for a in profile.analyzers
    ]
    path = Path(directory).resolve() / "decoded.csv"
    capture.export_data_table(filepath=str(path), analyzers=handles)
    return path
