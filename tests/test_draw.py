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
