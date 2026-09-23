from pathlib import Path

import pytest

from saleae_tools.profile import Profile, Trigger, load_profile, parse_channels


def test_channel_ranges_preserve_order():
    assert parse_channels("10, 2-4,0") == [10, 2, 3, 4, 0]


@pytest.mark.parametrize("value", ["", "0,", "-1", "0-16", "3-1", "a", "1,0-2", "0-999999999"])
def test_bad_channels(value):
    with pytest.raises(ValueError):
        parse_channels(value)


def test_named_analyzer_channels(tmp_path):
    path = tmp_path / "bench.toml"
    path.write_text("""
version = 1
[signals]
cs_n = 10
sclk = 2
mosi = 0
[[analyzers]]
name = "SPI"
[analyzers.channels]
Clock = "sclk"
MOSI = "mosi"
Enable = "cs_n"
[analyzers.settings]
"Bits per Transfer" = "8 Bits per Transfer (Standard)"
""")
    profile = load_profile(path)
    assert profile.channels == [0, 2, 10]
    assert profile.signal_names == ["mosi", "sclk", "cs_n"]
    assert profile.analyzers[0].settings["Clock"] == 2
    assert profile.analyzers[0].label == "SPI"


@pytest.mark.parametrize(
    "text",
    [
        "version = 2\n[signals]\na = 0",
        "version = true\n[signals]\na = 0",
        "version = 1\n[signals]\na = true",
        "version = 1\n[signals]\na = 0\nb = 0",
        'version = 1\n[signals]\n"bad name" = 0',
        "version = 1\n[signals]\na = 16",
        "version = 1\n[signals]\na = -1",
        "version = 1\n[capture]\nduration_s = nan\n[signals]\na = 0",
        "version = 1\n[capture]\nsample_rate = true\n[signals]\na = 0",
        "version = 1\n[capture]\nduration_s = false\n[signals]\na = 0",
        "version = 1\n[capture]\nseconds = 1\n[signals]\na = 0",
        'version = 1\n[signals]\na = 0\n[[analyzers]]\nname = "SPI"\n[analyzers.channels]\nClock = "missing"',
        'version = 1\n[signals]\na = 0\n[[analyzers]]\nname = "SPI"\n[analyzers.settings]\nClock = [0]',
        'version = 1\n[signals]\na = 0\n[[analyzers]]\nname = "SPI"\n[analyzers.channels]\nClock = "a"\n[analyzers.settings]\nClock = 0',
        'version = 1\n[signals]\na = 0\n[[analyzers]]\nname = "I2C"\n[[analyzers]]\nname = "I2C"',
    ],
)
def test_invalid_profile(tmp_path, text):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_profile(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_rate", 0),
        ("sample_rate", -1),
        ("duration_s", 0),
        ("duration_s", float("inf")),
        ("threshold_v", 5.0),
    ],
)
def test_invalid_acquisition(field, value):
    profile = Profile()
    setattr(profile, field, value)
    with pytest.raises(ValueError):
        profile.validate()


@pytest.mark.parametrize("path", sorted((Path(__file__).parents[1] / "examples").glob("*.toml")))
def test_example_profiles(path):
    profile = load_profile(path)
    assert profile.channels


@pytest.mark.parametrize(
    "kwargs",
    [
        {"signal": "missing"},
        {"edge": "high"},
        {"pre_trigger_s": -1},
        {"post_trigger_s": 0},
        {"timeout_s": 0.01},
        {"timeout_s": float("inf")},
        {"pre_trigger_s": True},
        {"post_trigger_s": float("nan")},
    ],
)
def test_invalid_triggers(kwargs):
    values = {"signal": "event", **kwargs}
    with pytest.raises(ValueError):
        Profile(signals={"event": 13}, trigger=Trigger(**values)).validate()


@pytest.mark.parametrize("table", ['edge = "rising"', 'signal = "event"\nunknown = 1'])
def test_invalid_trigger_tables(tmp_path, table):
    path = tmp_path / "bad.toml"
    path.write_text("version = 1\n[signals]\nevent = 13\n[trigger]\n" + table)
    with pytest.raises(ValueError):
        load_profile(path)


def test_all_profiles_keep_the_fixed_harness():
    root = Path(__file__).parents[1] / "examples"
    board = load_profile(root / "icepi-board.toml")
    assert board.channels == list(range(16))
    assert board.trigger.signal == "event"
    for path in root.glob("icepi-*.toml"):
        for signal, channel in load_profile(path).signals.items():
            canonical = "serial_data" if signal == "ui_in_0" else signal
            assert channel == board.signals[canonical], (path, signal)
