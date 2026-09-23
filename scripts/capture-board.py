#!/usr/bin/env python3
"""Acquire numbered, triggered board runs using the fixed Saleae harness.

Run with `uv run python scripts/capture-board.py --help` from the checkout.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from saleae_tools.cli import main as slt_main


def positive_count(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("count must be at least 1")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", default="board-1", help="board identity recorded in run.json")
    parser.add_argument(
        "--protocol",
        default="board",
        choices=["board", "uart", "spi", "i2c", "loader", "pin-through"],
    )
    parser.add_argument("--trigger", default="event", help="named signal, e.g. event, cs_n, rst_n")
    parser.add_argument("--edge", choices=["rising", "falling"], default="rising")
    parser.add_argument("--pre", type=float, default=0.01)
    parser.add_argument("--post", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--count", type=positive_count, default=1)
    parser.add_argument("--output-root", type=Path, default=Path("captures"))
    parser.add_argument("--note", default="", help="test case, RTL revision and bitstream hash")
    parser.add_argument("--device", help="Saleae device ID")
    parser.add_argument("--port", type=int, default=10430)
    parser.add_argument(
        "--dry-run", action="store_true", help="validate without connecting or writing"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.board):
        parser.error("--board must contain only letters, digits, hyphens and underscores")
    root = Path(__file__).resolve().parents[1]
    for index in range(1, args.count + 1):
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        output = args.output_root / args.board / f"{stamp}-{args.protocol}-{index:03d}"
        command = [
            "capture",
            "--profile",
            str(root / "examples" / f"icepi-{args.protocol}.toml"),
            "--trigger",
            args.trigger,
            "--edge",
            args.edge,
            "--pre",
            str(args.pre),
            "--post",
            str(args.post),
            "--timeout",
            str(args.timeout),
            "--port",
            str(args.port),
            "--output",
            str(output),
            "--note",
            f"board={args.board}; run={index}/{args.count}; {args.note}",
            "--save",
            "--vcd",
            "--json",
        ]
        if args.device:
            command.extend(["--device", args.device])
        if args.dry_run:
            command.append("--dry-run")
        print(f"Run {index}/{args.count}: {output}", file=sys.stderr, flush=True)
        # Keep acquisition in this process so Ctrl-C can finish capture cleanup.
        result = slt_main(command)
        if result:
            return result
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
