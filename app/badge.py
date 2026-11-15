"""The on-screen rate badge, handed to the worker to draw (v2.6.0).

The badge used to be drawn on the HUD layer, and since its numbers change on
every redraw that layer was flipped ten times a second - each flip of a
full-screen layered window costs the compositor a frame, and with the counter
on a quarter of a video's frames reached the screen a refresh off (#166).

The client still renders it - same font, theme and corner, display.py - but
into this shared bitmap, and the worker blends it over each frame it presents
(native/badge.inl). The layout of the mapping is the worker's BadgeHeader: a
32-byte header, then WIDTH x HEIGHT premultiplied RGBA8. The sequence is 0
while a bitmap is being written and a new non-zero value once it is whole.

The header's corner is 0-3 for the four corners, with margin and row as they
always were. Corner 4 is "custom", placed by two permille values: row is the
height position and reserved the width position, each 0..1000 of the room the
margin leaves (0 = at the left or top margin, 1000 = at the right or bottom).
"""
from __future__ import annotations

import mmap
import os
import struct
import uuid

WIDTH, HEIGHT = 512, 64
MAGIC = 0x45474442                 # "BDGE"
HEADER_FMT = "<8I"                 # magic, seq, w, h, corner, margin, row, reserved
HEADER_SIZE = struct.calcsize(HEADER_FMT)
CORNERS = {"tl": 0, "tr": 1, "bl": 2, "br": 3, "custom": 4}


def permille(fraction: float) -> int:
    """A 0..1 position as the header's 0..1000, clamped."""
    return int(round(min(1.0, max(0.0, float(fraction))) * 1000))


class BadgeChannel:
    """The client's end: one mapping for the session, rewritten on change."""

    def __init__(self) -> None:
        self.name = f"NeuralScreenBadge_{os.getpid()}_{uuid.uuid4().hex[:6]}"
        self._mm = mmap.mmap(-1, HEADER_SIZE + WIDTH * HEIGHT * 4, tagname=self.name)
        self._seq = 0
        self._last = None
        self.hide()

    def _write(self, pixels: bytes | None, w: int, h: int, corner: int,
               margin: int, row: int, x_permille: int = 0) -> None:
        mm = self._mm
        # Sequence 0 first: the worker never copies a bitmap mid-write.
        mm[4:8] = struct.pack("<I", 0)
        if pixels:
            stride = w * 4
            for y in range(h):
                at = HEADER_SIZE + y * WIDTH * 4
                mm[at:at + stride] = pixels[y * stride:(y + 1) * stride]
        self._seq = self._seq % 0xFFFFFFFE + 1
        mm[0:HEADER_SIZE] = struct.pack(HEADER_FMT, MAGIC, self._seq, w, h,
                                        corner, margin, row, x_permille)

    def publish(self, pixels: bytes, w: int, h: int, corner: str,
                margin: int, row: int, x_permille: int = 0) -> bool:
        """A new badge, premultiplied RGBA of w x h; True when it changed.

        Only a changed badge is written: the worker uploads on a new sequence,
        and the same bitmap again would be the work this module exists to save.
        For corner "custom", row is the height position and x_permille the
        width position (see the module docstring)."""
        w, h = min(int(w), WIDTH), min(int(h), HEIGHT)
        key = (bytes(pixels), w, h, corner, int(margin), int(row), int(x_permille))
        if key == self._last:
            return False
        self._last = key
        self._write(pixels, w, h, CORNERS.get(corner, 1), int(margin), int(row),
                    int(x_permille))
        return True

    def hide(self) -> bool:
        if self._last == "hidden":
            return False
        self._last = "hidden"
        self._write(None, 0, 0, 1, 0, 0)
        return True

    def close(self) -> None:
        try:
            self._mm.close()
        except Exception:
            pass
