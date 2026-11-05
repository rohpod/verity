"""Item sizes and capacity units, from AWS's published rules (ADR 0013), so costs can be
measured instead of guessed. These are estimates: moto reports no capacity for transactions.

- An item's size is the sum, over its attributes, of the name in UTF-8 bytes plus the value.
  A number is about one byte per two significant digits, plus one byte.
- A write unit is 1 KB, rounded up per item; a transactional write costs twice that.
- A read unit is 4 KB for a strongly consistent read, half that for an eventually consistent
  one. A query or scan adds up the items it reads before rounding up to 4 KB.
"""

import math
from collections.abc import Iterable

KB = 1024
READ_UNIT_BYTES = 4 * KB
WRITE_UNIT_BYTES = KB


def _number_bytes(text: str) -> int:
    digits = text.lstrip("+-").replace(".", "").lstrip("0").rstrip("0")
    return math.ceil(len(digits) / 2) + 1


def item_size(item: dict[str, dict[str, str]]) -> int:
    """Size in bytes of an item in the SDK's typed form (`{"S": ...}` or `{"N": ...}`)."""
    size = 0
    for name, value in item.items():
        ((kind, content),) = value.items()
        size += len(name.encode()) + (
            len(content.encode()) if kind == "S" else _number_bytes(content)
        )
    return size


def write_units(size: int, *, transactional: bool = False) -> int:
    units = max(1, math.ceil(size / WRITE_UNIT_BYTES))
    return units * 2 if transactional else units


def read_units(sizes: Iterable[int], *, consistent: bool = True) -> float:
    """Units for reading these items in one request."""
    units = math.ceil(sum(sizes) / READ_UNIT_BYTES)
    return float(units) if consistent else units / 2
