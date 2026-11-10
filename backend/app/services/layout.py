"""Grid placement for plate mosaics.

The scanner layout follows the stage path used by the imaging rig:
even columns run top to bottom, odd columns run bottom to top.
For a 7×4 plate that produces:

    1  14  15  28
    2  13  16  27
    3  12  17  26
    4  11  18  25
    5  10  19  24
    6   9  20  23
    7   8  21  22
"""

import re


def slots(rows: int, cols: int, layout: str) -> list[tuple[int, int]]:
    if rows < 1 or cols < 1:
        raise ValueError("Rows and columns must be at least 1.")
    if layout == "row":
        return [(r, c) for r in range(rows) for c in range(cols)]
    if layout == "scanner":
        placed: list[tuple[int, int]] = []
        for col in range(cols):
            row_order = range(rows) if col % 2 == 0 else range(rows - 1, -1, -1)
            for row in row_order:
                placed.append((row, col))
        return placed
    raise ValueError("Layout must be 'row' or 'scanner'.")


def natural_key(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name or "")]
