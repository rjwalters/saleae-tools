"""Offline decoding of the program loader's custom synchronous serial interface.

The iCEPi program loader (``docs/bringup.md`` bring-up stage 2,
``examples/icepi-loader.toml``) shifts fixed-width words MSB-first on one data
line while a mode line is held asserted. That interface is **not SPI** — there
is no chip select, no second data direction, and no stock Logic 2 analyzer for
it — but its wire behaviour is exactly the gated-interval case the SPI decoder
in :mod:`saleae_tools.spi` already implements: an enable line bounds an
interval, and data is sampled on one clock edge inside it.

So this module is a thin adapter, not a second decoder. It delegates to
:func:`saleae_tools.spi.decode` and re-exports that engine's result types; it
exists to give the loader a non-SPI name, a non-SPI CLI verb (``slt
syncserial``), and a flag surface that fits a one-direction interface:
``--edge rising|falling`` in place of SPI's ``--mode 0..3``, and an enable
whose active level is set by ``--enable-active-low``.
"""

from __future__ import annotations

from saleae_tools import spi
from saleae_tools.binexport import DigitalExport
from saleae_tools.spi import Decoded, Transaction

__all__ = ["Decoded", "Transaction", "decode"]

EDGES = ("rising", "falling")


def decode(
    clk: DigitalExport,
    data: DigitalExport,
    enable: DigitalExport,
    *,
    bits: int = 16,
    msb_first: bool = True,
    edge: str = "rising",
    enable_active_high: bool = True,
) -> Decoded:
    """Decode fixed-width words shifted on ``data`` while ``enable`` is asserted.

    ``enable`` is required: every stage-2 capture drives MODE, and without a
    gate there is no interval to anchor word boundaries to. Each asserted
    interval becomes one :class:`~saleae_tools.spi.Transaction`, whose ``mosi``
    field holds that interval's words (``cmd_syncserial`` reports it as
    ``words``); ``miso`` is always None, there being one data direction.

    Data is sampled on the rising clock edge by default, or the falling edge
    with ``edge="falling"``. Only two sampling behaviours exist here, so SPI's
    four CPOL/CPHA modes collapse to this pair: SPI modes 0 and 3 both sample
    rising, 1 and 2 both sample falling.

    Bits left over at the end of an interval are reported as
    ``leftover_bits`` rather than padded into a word. Chunks are decoded
    independently, and an interval still asserted at a chunk end is counted in
    ``truncated`` instead of being decoded from missing data.
    """
    if edge not in EDGES:
        raise ValueError("edge must be rising or falling")
    return spi.decode(
        clk,
        data,
        None,
        enable,
        mode=0 if edge == "rising" else 1,
        bits=bits,
        msb_first=msb_first,
        cs_active_low=not enable_active_high,
    )
