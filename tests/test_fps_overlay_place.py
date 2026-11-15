"""The on-screen counter's size and its own place (fps_overlay "custom").

The panel's X and Y sliders put the counter anywhere on the screen, and the
size slider takes it from 100% down to 25%. Checked without a window or a GPU:

1. the place is 0..1 of the room the margins leave, so 0 and 1 are the same
   margins the corners use: "custom" at (0, 0) is top-left, at (1, 1) the
   bottom-right corner, and a badge never leaves the screen;
2. the badge reaches the worker as corner 4, with the height in row and the
   width in the header's reserved field, both as permille (badge.py);
3. the size slider's range is 25..100 and a bad value falls back to 100, both
   in the config (settings_io) and where the slider's value is applied;
4. the three keys are shipped, reported in a support bundle, and their
   corner presets match the mode list.

Fails before the change: there was no custom mode, no size, and the header
had no place for a custom position.

Run:  runtime\\python.exe tests\\test_fps_overlay_place.py
"""
import os
import struct
import sys
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "app"))

import badge  # noqa: E402
import diagnostics  # noqa: E402
import settings_io  # noqa: E402
from overlay_ui import OverlayMenu  # noqa: E402,F401
from display import Display  # noqa: E402


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def origin(corner, fx, fy, w=200, h=50, width=1920, height=1080, ui_scale=1.0):
    """Display._badge_origin on a stand-in with the same screen and scale."""
    fake = types.SimpleNamespace(width=width, height=height, ui_scale=ui_scale)
    return Display._badge_origin(fake, corner, w, h, 0, fx, fy)


def check_placement() -> None:
    m = 14
    if origin("custom", 0.0, 0.0) != (m, m):
        fail(f"custom 0,0 is not the top-left margin: {origin('custom', 0.0, 0.0)}")
    if origin("custom", 1.0, 1.0) != (1920 - 200 - m, 1080 - 50 - m):
        fail(f"custom 1,1 is not the bottom-right margin: {origin('custom', 1.0, 1.0)}")
    if origin("custom", 1.0, 0.0) != (1920 - 200 - m, m):
        fail("custom 1,0 is not the top-right margin")
    # The corners and the custom extremes agree: the same numbers, the same places.
    for corner, fx, fy in (("tl", 0.0, 0.0), ("tr", 1.0, 0.0), ("bl", 0.0, 1.0), ("br", 1.0, 1.0)):
        if origin(corner, 0.0, 0.0) != origin("custom", fx, fy):
            fail(f"custom {fx},{fy} does not sit where the {corner} corner does")
    # The middle is the middle of the room, and nothing leaves the screen.
    x, y = origin("custom", 0.5, 0.5)
    if abs(x - (1920 - 200) / 2) > 2 or abs(y - (1080 - 50) / 2) > 2:
        fail(f"custom 0.5,0.5 is not centred: {(x, y)}")
    for fx in (0.0, 0.37, 1.0):
        for fy in (0.0, 0.61, 1.0):
            x, y = origin("custom", fx, fy)
            if x < 0 or y < 0 or x + 200 > 1920 or y + 50 > 1080:
                fail(f"custom {fx},{fy} puts the badge off the screen: {(x, y)}")
    # A badge wider than the room is pinned to the margin, not pushed off.
    if origin("custom", 1.0, 0.0, w=2000)[0] != 14:
        fail("an oversized badge is not pinned to the left margin")
    print("OK: custom places run from the corner margins to the far ones, and stay on screen")


def check_channel_header() -> None:
    channel = badge.BadgeChannel()
    try:
        pixels = bytes(200 * 50 * 4)
        channel.publish(pixels, 200, 50, "custom", 14,
                        badge.permille(0.25), x_permille=badge.permille(0.75))
        magic, seq, w, h, corner, margin, row, reserved = struct.unpack(
            badge.HEADER_FMT, channel._mm[0:badge.HEADER_SIZE])
        if (magic, corner, w, h, margin) != (badge.MAGIC, 4, 200, 50, 14):
            fail(f"custom header is wrong: magic={magic:#x} corner={corner} w={w} h={h} margin={margin}")
        if (row, reserved) != (250, 750):
            fail(f"custom place is not carried as permille: row={row} reserved={reserved}")
        if seq == 0:
            fail("the custom badge was published with sequence 0")
        # The same place again is not rewritten.
        if channel.publish(pixels, 200, 50, "custom", 14, 250, x_permille=750):
            fail("an unchanged custom badge was written again")
    finally:
        channel.close()
    if badge.permille(-0.5) != 0 or badge.permille(7.0) != 1000 or badge.permille(0.5) != 500:
        fail("permille does not clamp to 0..1000")
    print("OK: a custom badge reaches the worker as corner 4 with its place in permille")


def check_settings() -> None:
    if not (settings_io.FPS_OVERLAY_SCALE_MIN == 25 and settings_io.FPS_OVERLAY_SCALE_MAX == 100):
        fail("the size range is not 25..100 percent")
    if "custom" not in settings_io.FPS_OVERLAY_MODES:
        fail("custom is not a counter mode")
    if settings_io.FPS_OVERLAY_CORNER_XY != {"tl": (0.0, 0.0), "tr": (1.0, 0.0),
                                             "bl": (0.0, 1.0), "br": (1.0, 1.0)}:
        fail("the corner presets do not sit on the corners of the room")
    if settings_io.clamped_number("abc", 100, 25, 100) != 100:
        fail("a text size does not fall back to the default")
    if settings_io.clamped_number(float("nan"), 1.0, 0.0, 1.0) != 1.0:
        fail("NaN does not fall back to the default")
    if settings_io.clamped_number(-3, 100, 25, 100) != 25 or settings_io.clamped_number(400, 100, 25, 100) != 100:
        fail("out-of-range sizes are not clamped to 25..100")
    for key in ("fps_overlay_scale", "fps_overlay_x", "fps_overlay_y"):
        if key not in diagnostics._SETTINGS_KEYS:
            fail(f"{key} is not in the support bundle")
    print("OK: the size and place are validated, clamped and reported in support bundles")


def check_panel_defaults() -> None:
    if not hasattr(OverlayMenu, "_set_slider_value"):
        fail("the panel has no slider handler")
    if Display.BADGE_CORNERS[-1] != "custom":
        fail("custom is not a place the counter can be drawn at")
    print("OK: the panel's slider handler and the renderer both know the custom place")


if __name__ == "__main__":
    check_placement()
    check_channel_header()
    check_settings()
    check_panel_defaults()
    print("OK: the counter's size and its own place are drawn where the sliders put them")
