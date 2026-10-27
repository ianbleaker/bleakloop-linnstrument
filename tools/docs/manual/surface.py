"""The orientation figure: the whole surface in Session Mode, split into its four parts."""

from BleakLoop.core import engine, layout

from . import draw
from .pads import blocks
from .scenes import SCENES, Layer

SLUG = "surface"


def svg():
    frame = engine.render(*SCENES[Layer.SESSION])
    grid = [block for block in blocks(Layer.SESSION) if block.columns == layout.GRID_COLUMNS]
    return draw.figure(
        "The surface in Session Mode",
        [
            draw.panel(frame, [1], {}, (), caption="Global"),
            draw.panel(frame, layout.GRID_COLUMNS, {}, grid, caption="Session window"),
            draw.panel(frame, [layout.SCENE_COLUMN], {}, (), caption="View"),
            draw.panel(frame, [layout.NAV_COLUMN], {}, (), caption="Navigation"),
        ],
    )
