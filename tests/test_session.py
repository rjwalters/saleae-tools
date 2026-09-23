import array
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from saleae_tools import automation, binexport, session
from saleae_tools.profile import Analyzer, Profile, Trigger


@pytest.fixture
def bench(monkeypatch):
    manager, capture = Mock(), Mock()
    manager.get_app_info.return_value.app_version = "test-logic"
    manager.get_devices.return_value = [
        SimpleNamespace(device_id="test-device", device_type="LOGIC_PRO_16", is_simulation=False)
    ]
    manager.load_capture.return_value = capture
    connect = Mock(return_value=nullcontext(manager))
    timed = Mock(return_value=capture)
    monkeypatch.setattr(automation, "connect", connect)
    monkeypatch.setattr(automation, "capture_timed", timed)
    monkeypatch.setattr(session, "version", lambda name: "test-client")

    def export_raw_data_binary(*, directory, digital_channels, analog_channels):
        assert Path(directory).is_absolute()
        assert analog_channels == []
        for channel in digital_channels:
            binexport.write_digital(
                Path(directory) / f"digital_{channel}.bin",
                binexport.DigitalExport(
                    0, [binexport.DigitalChunk(channel % 2, 0, 1, array.array("d", [0.2, 0.4]))]
                ),
            )

    def save_capture(*, filepath):
        assert Path(filepath).is_absolute()
        Path(filepath).write_bytes(b"fake capture; only loaded by the mock")

    def export_data_table(*, filepath, analyzers):
        assert Path(filepath).is_absolute()
        Path(filepath).write_text("name,type,start_time,duration,data\nspi,result,0,0.1,0x55\n")

    capture.export_raw_data_binary.side_effect = export_raw_data_binary
    capture.save_capture.side_effect = save_capture
    capture.export_data_table.side_effect = export_data_table
    return manager, capture, connect, timed


def test_capture_bundle_has_named_signals_decoding_and_provenance(tmp_path, monkeypatch, bench):
    manager, capture, connect, timed = bench
    monkeypatch.chdir(tmp_path)
    profile = Profile(
        name="spi",
        signals={"cs_n": 10, "sclk": 2, "mosi": 0},
        duration_s=0.01,
        analyzers=[Analyzer("SPI", "spi", {"Clock": 2, "MOSI": 0, "Enable": 10})],
    )
    result = session.run_session(
        profile, "capture", save=True, vcd=True, note="RTL abc123; test 55"
    )
    assert result["status"] == "complete"
    assert result["device"]["device_id"] == "test-device"
    assert result["acquisition"]["duration_s"] == 0.01
    assert result["note"] == "RTL abc123; test 55"
    assert result["logic2_version"] == "test-logic"
    assert result["automation_version"] == "test-client"
    assert result == json.loads((tmp_path / "capture/run.json").read_text())
    assert {a["file"] for a in result["artifacts"]} == {
        "digital_0.bin",
        "digital_2.bin",
        "digital_10.bin",
        "capture.sal",
        "capture.vcd",
        "decoded.csv",
    }
    for artifact in result["artifacts"]:
        data = (tmp_path / "capture" / artifact["file"]).read_bytes()
        assert artifact["sha256"] == hashlib.sha256(data).hexdigest()
    vcd = (tmp_path / "capture/capture.vcd").read_text()
    assert vcd.index("mosi") < vcd.index("sclk") < vcd.index("cs_n")
    assert timed.call_args.kwargs["digital_channels"] == [0, 2, 10]
    assert timed.call_args.kwargs["device_id"] == "test-device"
    capture.add_analyzer.assert_called_once_with(
        "SPI", label="spi", settings=profile.analyzers[0].settings
    )
    capture.close.assert_called_once()


def test_loaded_capture_uses_absolute_path_and_unknown_acquisition(tmp_path, monkeypatch, bench):
    manager, capture, connect, timed = bench
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "original.sal"
    source.write_bytes(b"mock saved capture")
    result = session.run_session(Profile(), "reexport", source="original.sal", vcd=True)
    manager.load_capture.assert_called_once_with(filepath=str(source))
    timed.assert_not_called()
    manager.get_devices.assert_not_called()
    assert result["source_capture"] == str(source)
    assert result["operation"] == "export"
    assert result["acquisition"] is None
    assert "device" not in result
    capture.close.assert_called_once()


@pytest.mark.parametrize(
    "method", ["export_raw_data_binary", "add_analyzer", "export_data_table", "save_capture"]
)
def test_failed_export_closes_capture_and_records_failure(tmp_path, bench, method):
    manager, capture, connect, timed = bench
    getattr(capture, method).side_effect = ValueError("export failed")
    profile = Profile(analyzers=[Analyzer("I2C", "i2c", {"SCL": 0, "SDA": 1})])
    with pytest.raises(ValueError, match="export failed"):
        session.run_session(profile, tmp_path / "failed", save=True)
    manifest = json.loads((tmp_path / "failed/run.json").read_text())
    assert manifest["status"] == "failed"
    assert "export failed" in manifest["error"]
    assert "completed_at" not in manifest
    capture.close.assert_called_once()


def test_never_overwrite_or_glob_old_capture(tmp_path, bench):
    manager, capture, connect, timed = bench
    old = tmp_path / "digital_7.bin"
    old.write_bytes(b"old data")
    with pytest.raises(ValueError, match="new or empty"):
        session.run_session(Profile(), tmp_path)
    connect.assert_not_called()
    assert old.read_bytes() == b"old data"


def test_validate_before_connecting(tmp_path, bench):
    manager, capture, connect, timed = bench
    with pytest.raises(ValueError, match="positive"):
        session.run_session(Profile(duration_s=-1), tmp_path / "invalid")
    with pytest.raises(ValueError, match="does not exist"):
        session.run_session(Profile(), tmp_path / "missing", source=tmp_path / "missing.sal")
    connect.assert_not_called()
    assert not (tmp_path / "invalid").exists()


def test_failed_wait_records_selected_device(tmp_path, bench):
    manager, capture, connect, timed = bench
    timed.side_effect = ValueError("capture failed")
    with pytest.raises(ValueError, match="capture failed"):
        session.run_session(Profile(), tmp_path)
    result = json.loads((tmp_path / "run.json").read_text())
    assert result["status"] == "failed"
    assert result["device"]["device_id"] == "test-device"


def test_cleanup_failure_preserves_export_error(tmp_path, bench):
    manager, capture, connect, timed = bench
    capture.export_raw_data_binary.side_effect = ValueError("original export failure")
    capture.close.side_effect = RuntimeError("cleanup failure")
    with pytest.raises(ValueError, match="original export failure"):
        session.run_session(Profile(), tmp_path)
    capture.close.assert_called_once()
    assert "original export failure" in json.loads((tmp_path / "run.json").read_text())["error"]


def test_trigger_started_metadata_precedes_exports(tmp_path, bench, monkeypatch):
    manager, capture, connect, timed = bench
    started = Mock()

    def triggered(*args, on_started, **kwargs):
        on_started()
        manifest = json.loads((tmp_path / "run.json").read_text())
        assert "capture_started_at" in manifest
        assert manifest["status"] == "running"
        capture.export_raw_data_binary.assert_not_called()
        return capture

    monkeypatch.setattr(automation, "capture_triggered", triggered)
    result = session.run_session(
        Profile(signals={"event": 13}, trigger=Trigger("event")), tmp_path, on_started=started
    )
    timed.assert_not_called()
    started.assert_called_once()
    assert result["status"] == "complete"
    assert result["acquisition"]["mode"] == "digital_trigger"
    assert result["acquisition"]["duration_s"] is None
    assert result["acquisition"]["trigger"]["signal"] == "event"
    capture.close.assert_called_once()


def test_timeout_never_exports_or_reports_success(tmp_path, bench, monkeypatch):
    manager, capture, connect, timed = bench
    failure = automation.CaptureTimeout("no edge")
    failure.add_note("Capture cleanup failed; check Logic 2")
    monkeypatch.setattr(automation, "capture_triggered", Mock(side_effect=failure))
    with pytest.raises(automation.CaptureTimeout):
        session.run_session(Profile(trigger=Trigger("digital_0")), tmp_path, save=True, vcd=True)
    result = json.loads((tmp_path / "run.json").read_text())
    assert result["status"] == "timeout"
    assert result["error_notes"] == failure.__notes__
    assert "artifacts" not in result
    assert "completed_at" not in result
    capture.export_raw_data_binary.assert_not_called()
    capture.save_capture.assert_not_called()
    assert list(tmp_path.iterdir()) == [tmp_path / "run.json"]
