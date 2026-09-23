from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from saleae_tools import automation
from saleae_tools.profile import Profile, Trigger


def test_wait_failure_closes_capture(monkeypatch):
    api = SimpleNamespace(
        LogicDeviceConfiguration=lambda **kwargs: kwargs,
        CaptureConfiguration=lambda **kwargs: kwargs,
        TimedCaptureMode=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(automation, "_api", lambda: api)
    manager = Mock()
    cap = manager.start_capture.return_value
    cap.wait.side_effect = RuntimeError("USB disconnected")
    cap.close.side_effect = RuntimeError("cleanup failed too")
    with pytest.raises(RuntimeError, match="USB disconnected"):
        automation.capture_timed(
            manager,
            device_id="bench",
            digital_channels=[0],
            sample_rate=100_000_000,
            duration_s=0.01,
        )
    cap.close.assert_called_once()


def test_device_selection_is_explicit():
    manager = Mock()
    manager.get_devices.return_value = []
    with pytest.raises(automation.AutomationError, match="no matching"):
        automation.select_device(manager)
    manager.get_devices.return_value = [
        SimpleNamespace(device_id="a", device_type="LOGIC_PRO_16", is_simulation=False),
        SimpleNamespace(device_id="b", device_type="LOGIC_PRO_16", is_simulation=False),
    ]
    with pytest.raises(automation.AutomationError, match="multiple"):
        automation.select_device(manager)
    assert automation.select_device(manager, "b").device_id == "b"
    manager.get_devices.assert_called_with(include_simulation_devices=True)


def test_binary_exports_use_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    capture = Mock()
    assert automation.export_binary(capture, "relative", [0], []) == tmp_path / "relative"
    capture.export_raw_data_binary.assert_called_once_with(
        directory=str(tmp_path / "relative"), digital_channels=[0], analog_channels=[]
    )


@pytest.fixture
def trigger_bench(monkeypatch):
    api = SimpleNamespace(
        LogicDeviceConfiguration=lambda **kwargs: kwargs,
        CaptureConfiguration=lambda **kwargs: kwargs,
        DigitalTriggerCaptureMode=lambda **kwargs: kwargs,
        DigitalTriggerType=SimpleNamespace(RISING="rise", FALLING="fall"),
    )
    monkeypatch.setattr(automation, "_api", lambda: api)
    wait = Mock()
    monkeypatch.setattr(automation, "_wait_for_trigger", wait)
    return Mock(), wait


def test_trigger_uses_named_wire_and_full_window(trigger_bench):
    manager, wait = trigger_bench
    started = Mock()
    profile = Profile(
        signals={"cs_n": 3, "event": 13}, trigger=Trigger("cs_n", "falling", 0.02, 0.1, 5)
    )
    capture = automation.capture_triggered(
        manager, device_id="board", profile=profile, on_started=started
    )
    cfg = manager.start_capture.call_args.kwargs
    assert cfg["device_configuration"]["enabled_digital_channels"] == [3, 13]
    trigger = cfg["capture_configuration"]["capture_mode"]
    assert trigger["trigger_channel_index"] == 3
    assert trigger["trigger_type"] == "fall"
    assert trigger["trim_data_seconds"] == pytest.approx(0.12)
    assert trigger["after_trigger_seconds"] == 0.1
    started.assert_called_once()
    wait.assert_called_once_with(capture, 5)
    capture.close.assert_not_called()


@pytest.mark.parametrize(
    "error", [automation.CaptureTimeout("timeout"), KeyboardInterrupt(), RuntimeError("USB")]
)
def test_trigger_failure_closes_without_stop(trigger_bench, error):
    manager, wait = trigger_bench
    wait.side_effect = error
    with pytest.raises(type(error)):
        automation.capture_triggered(
            manager, device_id="board", profile=Profile(trigger=Trigger("digital_0"))
        )
    manager.start_capture.return_value.close.assert_called_once()
    manager.start_capture.return_value.stop.assert_not_called()


def test_trigger_cleanup_failure_is_reported(trigger_bench):
    manager, wait = trigger_bench
    wait.side_effect = automation.CaptureTimeout("timeout")
    manager.start_capture.return_value.close.side_effect = RuntimeError("disconnected")
    with pytest.raises(automation.CaptureTimeout) as error:
        automation.capture_triggered(
            manager, device_id="board", profile=Profile(trigger=Trigger("digital_0"))
        )
    assert "disconnected" in error.value.__notes__[0]


def test_wait_deadline_against_local_grpc_server():
    # Exercise actual transport cancellation with synthetic responses, no Logic 2.
    import time
    from concurrent.futures import ThreadPoolExecutor

    grpc = pytest.importorskip("grpc")
    proto = pytest.importorskip("saleae.grpc.saleae_pb2")
    service = pytest.importorskip("saleae.grpc.saleae_pb2_grpc")

    class Server(service.ManagerServicer):
        def WaitCapture(self, request, context):
            if request.capture_id == 1:
                return proto.WaitCaptureReply()
            while context.is_active():
                time.sleep(0.005)
            return proto.WaitCaptureReply()

    with ThreadPoolExecutor(max_workers=2) as workers:
        server = grpc.server(workers)
        service.add_ManagerServicer_to_server(Server(), server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                grpc.channel_ready_future(channel).result(timeout=2)
                capture = SimpleNamespace(
                    manager=SimpleNamespace(stub=service.ManagerStub(channel)), capture_id=1
                )
                automation._wait_for_trigger(capture, 1)
                capture.capture_id = 2
                with pytest.raises(automation.CaptureTimeout, match="did not complete"):
                    automation._wait_for_trigger(capture, 0.05)
        finally:
            server.stop(0).wait(timeout=2)
