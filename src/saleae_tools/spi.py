"""Offline SPI decoding of digital exports, independent of Logic 2."""

from __future__ import annotations

from dataclasses import dataclass, field

from saleae_tools.binexport import DigitalChunk, DigitalExport


@dataclass
class Transaction:
    start_s: float  # CS assertion (or start of the shared span if already asserted)
    end_s: float  # CS deassertion
    mosi: list[int] = field(default_factory=list)
    miso: list[int] | None = None
    leftover_bits: int = 0  # trailing sampled bits that did not fill a word


@dataclass
class Decoded:
    transactions: list[Transaction] = field(default_factory=list)
    truncated: int = 0  # transactions cut off by a chunk end; never decoded

    @property
    def leftover_bits(self) -> int:
        return sum(t.leftover_bits for t in self.transactions)


def _words(bits: list[int], width: int, msb_first: bool) -> tuple[list[int], int]:
    n = len(bits) // width
    out = []
    for w in range(n):
        word = bits[w * width : (w + 1) * width]
        if msb_first:
            word = word[::-1]
        out.append(sum(b << k for k, b in enumerate(word)))
    return out, len(bits) - n * width


def decode(
    sclk: DigitalExport,
    mosi: DigitalExport,
    miso: DigitalExport | None,
    cs_n: DigitalExport,
    *,
    mode: int = 0,
    bits: int = 8,
    msb_first: bool = True,
    cs_active_low: bool = True,
) -> Decoded:
    """Decode SPI transactions. Chunks are paired by index; each is decoded alone.

    A transaction runs from CS assertion to deassertion; the shared span of the
    paired chunks bounds it. Data is sampled on the SCLK edge below::

        mode  CPOL  CPHA  sampling edge
        0     0     0     rising  (leading)
        1     0     1     falling (trailing)
        2     1     0     falling (leading)
        3     1     1     rising  (trailing)

    A transaction still asserted at the end of the shared span is counted in
    ``truncated`` instead of being decoded from missing data.
    """
    if mode not in (0, 1, 2, 3):
        raise ValueError("mode must be 0..3")
    if bits < 1:
        raise ValueError("bits must be >= 1")
    sample_level = 1 if mode in (0, 3) else 0  # level of SCLK after the sampling edge
    active = 0 if cs_active_low else 1
    exports = [sclk, mosi, cs_n] + ([miso] if miso is not None else [])
    if len({len(e.chunks) for e in exports}) != 1:
        raise ValueError("channel exports have different chunk counts")
    out = Decoded()
    for i, cs in enumerate(cs_n.chunks):
        chunks = [e.chunks[i] for e in exports]
        begin = max(c.begin_time for c in chunks)
        end = min(c.end_time for c in chunks)
        ck, cm, mi = sclk.chunks[i], mosi.chunks[i], miso.chunks[i] if miso is not None else None
        # Walk CS into (assert, deassert) intervals; None = no deassertion in span.
        events = [(begin, cs.level_at(begin))]
        events += [(t, cs.level_at(t)) for t in cs.transitions if begin < t <= end]
        start: float | None = None
        for t, lvl in events:
            if lvl == active and start is None:
                start = t
            elif lvl != active and start is not None:
                out.transactions.append(
                    _transaction(ck, cm, mi, start, t, sample_level, bits, msb_first)
                )
                start = None
        if start is not None:
            out.truncated += 1
    return out


def _transaction(
    ck: DigitalChunk,
    cm: DigitalChunk,
    mi: DigitalChunk | None,
    start: float,
    stop: float,
    sample_level: int,
    bits: int,
    msb_first: bool,
) -> Transaction:
    mosi_bits: list[int] = []
    miso_bits: list[int] = []
    for k, t in enumerate(ck.transitions):
        if t <= start or t >= stop:
            continue
        if (ck.initial_state ^ ((k + 1) & 1)) != sample_level:
            continue
        mosi_bits.append(cm.level_at(t))
        if mi is not None:
            miso_bits.append(mi.level_at(t))
    words, leftover = _words(mosi_bits, bits, msb_first)
    txn = Transaction(start, stop, words, None, leftover)
    if mi is not None:
        txn.miso = _words(miso_bits, bits, msb_first)[0]
    return txn
