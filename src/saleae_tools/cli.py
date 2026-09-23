"""``slt`` command line. Only acquisition and .sal export need the optional SDK."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from saleae_tools import __version__
from saleae_tools.binexport import (
    AnalogExport,
    DigitalExport,
    read_digital,
    read_export,
)
from saleae_tools.profile import Profile, Trigger, load_profile, parse_channels
from saleae_tools.vcd import write_vcd


def _describe(path: Path) -> dict[str, object]:
    e = read_export(path)
    if isinstance(e, DigitalExport):
        return {
            "path": str(path),
            "kind": "digital",
            "version": e.version,
            "chunks": len(e.chunks),
            "begin_time": e.begin_time,
            "end_time": e.end_time,
            "num_transitions": e.num_transitions,
            "sample_rate": e.chunks[0].sample_rate if e.chunks else None,
        }
    assert isinstance(e, AnalogExport)
    w = e.waveforms[0] if e.waveforms else None
    return {
        "path": str(path),
        "kind": "analog",
        "version": e.version,
        "waveforms": len(e.waveforms),
        "begin_time": w.begin_time if w else None,
        "end_time": w.end_time if w else None,
        "sample_rate": w.sample_rate if w else None,
        "downsample": w.downsample if w else None,
        "num_samples": e.num_samples,
    }


def cmd_info(args: argparse.Namespace) -> int:
    rows = [_describe(Path(p)) for p in args.files]
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    for r in rows:
        if r["kind"] == "digital":
            print(
                f"{r['path']}: digital v{r['version']} chunks={r['chunks']} "
                f"t={r['begin_time']:.6f}..{r['end_time']:.6f}s "
                f"transitions={r['num_transitions']}"
            )
        else:
            print(
                f"{r['path']}: analog v{r['version']} waveforms={r['waveforms']} "
                f"t={r['begin_time']:.6f}..{r['end_time']:.6f}s "
                f"rate={r['sample_rate']}/{r['downsample']} samples={r['num_samples']}"
            )
    return 0


def _channel_index(path: Path) -> int:
    """``digital_7.bin`` -> 7; anything else sorts last in name order."""
    stem = path.stem
    if "_" in stem and stem.rsplit("_", 1)[1].isdigit():
        return int(stem.rsplit("_", 1)[1])
    return 1 << 30


def cmd_vcd(args: argparse.Namespace) -> int:
    paths = sorted((Path(p) for p in args.files), key=lambda p: (_channel_index(p), p.name))
    exports = [read_digital(p) for p in paths]
    names = args.names.split(",") if args.names else [p.stem for p in paths]
    if len(names) != len(exports):
        print(f"--names has {len(names)} entries for {len(exports)} files", file=sys.stderr)
        return 2
    n = write_vcd(args.output, exports, names, timescale=args.timescale, module=args.module)
    print(f"wrote {args.output}: {len(exports)} signals, {n} events", file=sys.stderr)
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    e = read_digital(Path(args.file))
    limit = args.limit
    emitted = 0
    for c in e.chunks:
        for t, s in c.states():
            print(f"{t:.9f}\t{s}")
            emitted += 1
            if limit and emitted >= limit:
                return 0
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    from saleae_tools import automation

    with automation.connect(port=args.port) as m:
        devs = automation.list_devices(m, include_simulation=args.simulation)
    if args.json:
        json.dump([d.__dict__ for d in devs], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for d in devs:
            tag = " (simulation)" if d.is_simulation else ""
            print(f"{d.device_id}\t{d.device_type}{tag}")
    return 0


def _capture_profile(args: argparse.Namespace) -> Profile:
    if args.profile:
        if args.channels is not None or args.names is not None:
            raise ValueError("edit [signals] in the profile instead of using --channels/--names")
        profile = load_profile(args.profile)
    else:
        channels = parse_channels(args.channels if args.channels is not None else "0-3")
        names = (
            args.names.split(",") if args.names is not None else [f"digital_{c}" for c in channels]
        )
        if len(names) != len(channels) or len(set(names)) != len(names):
            raise ValueError("--names must give one unique name per channel, in --channels order")
        profile = Profile(signals=dict(zip(names, channels, strict=True)))
    for option, field in (
        ("rate", "sample_rate"),
        ("seconds", "duration_s"),
        ("threshold", "threshold_v"),
    ):
        if (value := getattr(args, option, None)) is not None:
            setattr(profile, field, value)
    if getattr(args, "timed", False):
        profile.trigger = None
    if (signal := getattr(args, "trigger", None)) is not None:
        profile.trigger = profile.trigger or Trigger(signal=signal)
        profile.trigger.signal = signal
    for option, field in (
        ("edge", "edge"),
        ("pre", "pre_trigger_s"),
        ("post", "post_trigger_s"),
        ("timeout", "timeout_s"),
    ):
        if (value := getattr(args, option, None)) is not None:
            if profile.trigger is None:
                raise ValueError(f"--{option} requires --trigger or a profile [trigger] table")
            setattr(profile.trigger, field, value)
    if profile.trigger and getattr(args, "seconds", None) is not None:
        raise ValueError("use --post for triggered captures; --seconds is for --timed captures")
    profile.validate()
    return profile


def cmd_capture(args: argparse.Namespace) -> int:
    from saleae_tools.session import run_session

    profile = _capture_profile(args)
    if args.dry_run:
        json.dump(asdict(profile), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if not args.output:
        raise ValueError("--output is required unless --dry-run is used")
    result = run_session(
        profile,
        args.output,
        device_id=getattr(args, "device", None),
        port=args.port,
        headless=args.headless,
        source=getattr(args, "file", None),
        save=args.save,
        vcd=args.vcd,
        note=args.note,
        on_started=lambda: print(
            "Capture started; waiting for trigger and post-trigger recording.",
            file=sys.stderr,
            flush=True,
        ),
    )
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(
            f"exported to {result['output']} (run.json records settings and artifacts)",
            file=sys.stderr,
        )
    return 0


def cmd_timing(args: argparse.Namespace) -> int:
    from saleae_tools.timing import measure

    rows = [{"path": p, **measure(read_digital(p))} for p in args.files]
    json.dump(rows, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_mcp_tools(args: argparse.Namespace) -> int:
    from saleae_tools.mcp import McpError, list_tools

    try:
        tools = list_tools(args.url)
    except McpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json:
        json.dump(tools, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    for t in tools:
        desc = (t.get("description") or "").strip().splitlines()
        print(f"{t['name']}\t{desc[0] if desc else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slt", description="Saleae Logic tools")
    p.add_argument("--version", action="version", version=f"slt {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="describe binary export files")
    s.add_argument("files", nargs="+")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("vcd", help="convert digital_*.bin exports to one VCD")
    s.add_argument("files", nargs="+")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--names", help="comma-separated signal names in channel order")
    s.add_argument("--timescale", default="1ns", choices=["1s", "1ms", "1us", "1ns", "1ps"])
    s.add_argument("--module", default="saleae")
    s.set_defaults(fn=cmd_vcd)

    s = sub.add_parser("dump", help="print (time, state) rows for one digital export")
    s.add_argument("file")
    s.add_argument("-n", "--limit", type=int, default=0)
    s.set_defaults(fn=cmd_dump)

    s = sub.add_parser("devices", help="list devices via a running automation server")
    s.add_argument("--port", type=int, default=10430)
    s.add_argument("--simulation", action="store_true", help="include simulation devices")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_devices)

    for verb, help_text in (
        ("capture", "timed or edge-triggered capture with decoding and VCD"),
        ("export", "re-export a saved .sal through Logic 2 (no device needed)"),
    ):
        s = sub.add_parser(verb, help=help_text)
        if verb == "export":
            s.add_argument("file", help="saved .sal capture")
        else:
            s.add_argument("--rate", type=int, help="digital sample rate (default: 100000000 S/s)")
            s.add_argument("--seconds", type=float, help="timed duration (default: 1 s)")
            s.add_argument(
                "--threshold", type=float, help="Logic Pro preset: 1.2, 1.8, 3.3 (default)"
            )
            s.add_argument("--device", help="device ID (default: the only real device)")
            mode = s.add_mutually_exclusive_group()
            mode.add_argument(
                "--trigger", metavar="SIGNAL", help="trigger on a named enabled signal"
            )
            mode.add_argument("--timed", action="store_true", help="disable the profile trigger")
            s.add_argument(
                "--edge", choices=["rising", "falling"], help="trigger edge (default: rising)"
            )
            s.add_argument(
                "--pre", type=float, help="requested pre-trigger history in seconds (default: .01)"
            )
            s.add_argument("--post", type=float, help="post-trigger seconds (default: .05)")
            s.add_argument(
                "--timeout",
                type=float,
                help="trigger + recording deadline in seconds (default: 30)",
            )
        s.add_argument("-o", "--output", help="new or empty export directory")
        s.add_argument("--profile", help="TOML bench profile")
        s.add_argument("--channels", help="digital channels, e.g. 0-3,7 (default: 0-3)")
        s.add_argument("--names", help="signal names in --channels order")
        s.add_argument("--port", type=int)
        s.add_argument("--headless", action="store_true", help="launch the native headless server")
        s.add_argument("--save", action="store_true", help="also save capture.sal with analyzers")
        s.add_argument("--vcd", action="store_true", help="also write capture.vcd")
        s.add_argument(
            "--note", default="", help="record firmware revision, wiring or test case in run.json"
        )
        s.add_argument(
            "--dry-run",
            action="store_true",
            help="validate/print profile without Logic 2 or file writes",
        )
        s.add_argument("--json", action="store_true", help="print the completed run manifest")
        s.set_defaults(fn=cmd_capture)

    s = sub.add_parser(
        "timing", help="JSON pulse/period measurements from digital exports (offline)"
    )
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_timing)

    s = sub.add_parser("mcp-tools", help="list tools exposed by the Logic 2 MCP server")
    s.add_argument("--url", default="http://127.0.0.1:10530")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_mcp_tools)
    return p


def main(argv: list[str] | None = None) -> int:
    from saleae_tools.automation import AutomationError

    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except (ValueError, OSError, AutomationError) as e:
        print(f"error: {e}", file=sys.stderr)
        for note in getattr(e, "__notes__", []):
            print(note, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
