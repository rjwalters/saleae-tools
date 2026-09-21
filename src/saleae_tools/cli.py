"""``slt`` command line. Stdlib-only except the ``capture``/``devices`` verbs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from saleae_tools import __version__
from saleae_tools.binexport import (
    AnalogExport,
    DigitalExport,
    ExportFormatError,
    read_digital,
    read_export,
)
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


def cmd_capture(args: argparse.Namespace) -> int:
    from saleae_tools import automation

    channels = [int(c) for c in args.channels.split(",")]
    ctx = (
        automation.launch(headless=True, port=args.port)
        if args.headless
        else automation.connect(port=args.port)
    )
    with ctx as m:
        cap = automation.capture_timed(
            m,
            device_id=args.device,
            digital_channels=channels,
            sample_rate=args.rate,
            duration_s=args.seconds,
            threshold_v=args.threshold,
        )
        out = automation.export_binary(cap, args.output, digital_channels=channels)
        if args.save:
            cap.save_capture(filepath=str(Path(args.output) / "capture.sal"))
        cap.close()
    print(f"exported to {out}", file=sys.stderr)
    if args.vcd:
        files = sorted(out.glob("digital_*.bin"), key=_channel_index)
        exports = [read_digital(p) for p in files]
        names = args.names.split(",") if args.names else [p.stem for p in files]
        write_vcd(out / "capture.vcd", exports, names)
        print(f"wrote {out / 'capture.vcd'}", file=sys.stderr)
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

    s = sub.add_parser("capture", help="timed digital capture -> binary export (+VCD)")
    s.add_argument("-o", "--output", required=True, help="export directory")
    s.add_argument("--channels", default="0,1,2,3", help="comma-separated digital channels")
    s.add_argument("--rate", type=int, default=100_000_000, help="digital sample rate (S/s)")
    s.add_argument("--seconds", type=float, default=1.0)
    s.add_argument("--threshold", type=float, default=3.3, help="logic threshold volts")
    s.add_argument("--device", default=None, help="device id (default: first device)")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--headless", action="store_true", help="launch the native headless server")
    s.add_argument("--save", action="store_true", help="also save capture.sal")
    s.add_argument("--vcd", action="store_true", help="also write capture.vcd")
    s.add_argument("--names", help="signal names for --vcd, in channel order")
    s.set_defaults(fn=cmd_capture)

    s = sub.add_parser("mcp-tools", help="list tools exposed by the Logic 2 MCP server")
    s.add_argument("--url", default="http://127.0.0.1:10530")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_mcp_tools)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except ExportFormatError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
