"""Capture/export lifecycle and a self-describing directory for each bench run."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from saleae_tools import __version__, automation
from saleae_tools.binexport import read_digital
from saleae_tools.profile import Profile
from saleae_tools.vcd import write_vcd


def _artifact(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest}


def run_session(
    profile: Profile,
    directory: str | Path,
    *,
    device_id: str | None = None,
    port: int | None = None,
    headless: bool = False,
    source: str | Path | None = None,
    save: bool = False,
    vcd: bool = False,
    note: str = "",
    on_started: Callable[[], None] | None = None,
) -> dict[str, object]:
    """Write exports and run.json; refuse to mix old and new capture artifacts.

    A saved capture's acquisition settings are unknown: profile settings are
    used only for channel selection, names and analyzers when re-exporting.
    """
    profile.validate()
    out = Path(directory).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output directory must be new or empty: {out}")
    source_path = Path(source).resolve() if source is not None else None
    if source_path is not None and not source_path.is_file():
        raise ValueError(f"saved capture does not exist: {source_path}")
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "operation": "export" if source_path else "capture",
        "started_at": datetime.now(UTC).isoformat(),
        "saleae_tools_version": __version__,
        "profile": asdict(profile),
        "acquisition": None
        if source_path
        else {
            "mode": "digital_trigger" if profile.trigger else "timed",
            "sample_rate": profile.sample_rate,
            "duration_s": None if profile.trigger else profile.duration_s,
            "threshold_v": profile.threshold_v,
            "trigger": asdict(profile.trigger) if profile.trigger else None,
        },
        "source_capture": str(source_path) if source_path else None,
        "note": note,
        "output": str(out),
    }

    def write_manifest() -> None:
        (out / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")

    write_manifest()
    try:
        ctx = (
            automation.launch(headless=True, port=port)
            if headless
            else automation.connect(port=port or automation.DEFAULT_PORT)
        )
        with ctx as manager:
            manifest["logic2_version"] = manager.get_app_info().app_version
            manifest["automation_version"] = version("logic2-automation")
            if source_path is None:
                device = automation.select_device(manager, device_id)
                manifest["device"] = asdict(device)
                write_manifest()
                if profile.trigger:

                    def started() -> None:
                        manifest["capture_started_at"] = datetime.now(UTC).isoformat()
                        write_manifest()
                        if on_started is not None:
                            on_started()

                    capture = automation.capture_triggered(
                        manager, device_id=device.device_id, profile=profile, on_started=started
                    )
                else:
                    capture = automation.capture_timed(
                        manager,
                        device_id=device.device_id,
                        digital_channels=profile.channels,
                        sample_rate=profile.sample_rate,
                        duration_s=profile.duration_s,
                        threshold_v=profile.threshold_v,
                    )
            else:
                capture = manager.load_capture(filepath=str(source_path))
            try:
                automation.export_binary(
                    capture, out, digital_channels=profile.channels, analog_channels=[]
                )
                paths = [out / f"digital_{channel}.bin" for channel in profile.channels]
                if decoded := automation.export_analyzers(capture, out, profile):
                    paths.append(decoded)
                if save:
                    saved = out / "capture.sal"
                    capture.save_capture(filepath=str(saved))
                    paths.append(saved)
            except BaseException:
                with suppress(Exception):
                    capture.close()
                raise
            else:
                capture.close()
        if vcd:
            # Use only the requested files, paired by channel number with their
            # names. Never glob in stale exports from an earlier run.
            exports = [read_digital(out / f"digital_{c}.bin") for c in profile.channels]
            vcd_path = out / "capture.vcd"
            write_vcd(vcd_path, exports, profile.signal_names)
            paths.append(vcd_path)
        manifest["artifacts"] = [_artifact(path) for path in paths]
        manifest["status"] = "complete"
        manifest["completed_at"] = datetime.now(UTC).isoformat()
        write_manifest()
    except BaseException as exc:
        manifest["status"] = "timeout" if isinstance(exc, automation.CaptureTimeout) else "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        if notes := getattr(exc, "__notes__", None):
            manifest["error_notes"] = notes
        with suppress(OSError):
            write_manifest()
        raise
    return manifest
