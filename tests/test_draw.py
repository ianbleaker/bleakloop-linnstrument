import re

from BleakLoop.core import engine
from tools.docs.manual import draw
from tools.docs.manual.scenes import SCENES, Layer


def width(svg):
    return int(re.search(r'width="(\d+)"', svg).group(1))


def test_two_one_column_panels_sit_between_one_panel_and_a_full_map():
    frame = engine.render(*SCENES[Layer.SESSION])
    one = draw.figure("One", [draw.panel(frame, [15], {}, ())])
    two = draw.figure(
        "Two",
        [
            draw.panel(frame, [15], {}, (), caption="normal"),
            draw.panel(frame, [16], {}, (), caption="shift"),
        ],
    )
    assert width(one) < width(two) < width(draw.map_svg(Layer.SESSION))
    assert ">normal</text>" in two and ">shift</text>" in two


def test_a_held_map_is_tinted_and_says_so():
    svg = draw.map_svg(Layer.SESSION_SHIFT)
    words, tint, _ = draw.HOLDS["shift"]
    assert f'fill="{tint}"' in svg and f">{words}</text>" in svg
    plain = draw.map_svg(Layer.SESSION)
    assert f'fill="{tint}"' not in plain and "HELD</text>" not in plain


def test_held_panels_tint_their_own_backdrop_and_caption():
    normal, shifted = SCENES[Layer.SESSION], SCENES[Layer.SESSION_SHIFT]
    svg = draw.figure(
        "Two",
        [
            draw.panel(engine.render(*normal), [16], {}, (), caption="normal"),
            draw.panel(engine.render(*shifted), [16], {}, (), held=draw.held_of(shifted[0])),
        ],
    )
    words, tint, colour = draw.HOLDS["shift"]
    assert f'fill="{tint}"' in svg
    assert f'fill="{colour}" text-anchor="middle">{words}</text>' in svg
