"""Parser for the 'Verbrauchsinformation' page (action=objverbmiet).

Kept free of Home Assistant imports so it can be tested standalone.
"""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import date

# Meter type is only encoded in the icon file name (images/mbt<N>.png).
METER_KINDS: dict[str, tuple[str, str]] = {
    "4": ("heat", "Heizung"),
    "6": ("warm_water", "Warmwasser"),
    "7": ("cold_water", "Kaltwasser"),
}

_HEADER_RE = re.compile(
    r'<img[^>]*src="images/mbt(\d+)\.png"[^>]*>\s*<h1[^>]*>([^<]*)</h1>', re.S
)
_TABLE_RE = re.compile(r"<table>(.*?)</table>", re.S)
_ROW_RE = re.compile(
    r"<td>\s*(\d{2})\.(\d{2})\.(\d{4})[^<]*</td>\s*<td>\s*(-?[\d.,]+)", re.S
)


@dataclass(frozen=True)
class Reading:
    date: date
    value: float


@dataclass
class Meter:
    number: str
    type_code: str
    readings: list[Reading] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return METER_KINDS.get(self.type_code, ("unknown", ""))[0]

    @property
    def label(self) -> str:
        return METER_KINDS.get(self.type_code, ("", f"Zähler (Typ {self.type_code})"))[
            1
        ]

    @property
    def latest(self) -> Reading | None:
        return self.readings[-1] if self.readings else None


def _to_float(raw: str) -> float:
    # German number format: "." thousands separator, "," decimal separator.
    return float(raw.replace(".", "").replace(",", "."))


def parse_meters(page: str) -> list[Meter]:
    headers = list(_HEADER_RE.finditer(page))
    meters: list[Meter] = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(page)
        chunk = page[header.end() : end]

        title = htmllib.unescape(header.group(2)).strip()
        number = re.sub(r"^Ger(ä|ae)t\s*", "", title).strip() or title

        readings: list[Reading] = []
        table = _TABLE_RE.search(chunk)
        if table:
            for d, m, y, raw in _ROW_RE.findall(table.group(1)):
                readings.append(Reading(date(int(y), int(m), int(d)), _to_float(raw)))
        readings.sort(key=lambda r: r.date)

        meters.append(
            Meter(number=number, type_code=header.group(1), readings=readings)
        )
    return meters


# A drop below this fraction of the previous peak is treated as a meter reset
# (e.g. at the annual cut-off date); smaller drops are portal corrections.
RESET_RATIO = 0.5


def consumption_sums(readings: list[Reading]) -> list[tuple[Reading, float]]:
    """Return (reading, cumulative consumption) pairs, starting at 0.

    - Leading zero readings (meter not active yet) are skipped.
    - Later zero readings are treated as missing data, not as a reset.
    - Small drops are ignored until the value exceeds the previous peak again,
      so corrections never produce negative consumption.
    - A drop below RESET_RATIO of the peak counts as a reset.
    """
    result: list[tuple[Reading, float]] = []
    total = 0.0
    peak: float | None = None
    for reading in readings:
        value = reading.value
        if value <= 0:
            continue
        if peak is None:
            peak = value
        elif value < peak * RESET_RATIO:
            total += value
            peak = value
        elif value > peak:
            total += value - peak
            peak = value
        result.append((reading, round(total, 6)))
    return result
