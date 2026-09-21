"""saleae-tools: agent-friendly tools for the Saleae Logic Pro 16.

The core package is stdlib-only. Anything that talks to a running Logic 2
(GUI or the native headless server) lives behind the ``automation`` extra.
"""

from saleae_tools.binexport import (
    AnalogExport,
    AnalogWaveform,
    DigitalChunk,
    DigitalExport,
    read_analog,
    read_digital,
    read_export,
    sniff,
)
from saleae_tools.vcd import write_vcd

__version__ = "0.1.0"

__all__ = [
    "AnalogExport",
    "AnalogWaveform",
    "DigitalChunk",
    "DigitalExport",
    "read_analog",
    "read_digital",
    "read_export",
    "sniff",
    "write_vcd",
]
