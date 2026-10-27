"""The Columns figures: one column each, a panel per layer, labelled from its own section."""

from BleakLoop.core import engine, layout

from . import draw
from .pads import section_labels
from .scenes import DEVICE_CLIP_HELD, SCENES, Layer

NORMAL = SCENES[Layer.SESSION]
SHIFT = SCENES[Layer.SESSION_SHIFT]

# slug -> (title, column, panels of (caption, (state, snapshot), section))
FIGURES = {
    "columns-global": (
        "Global column",
        1,
        (("normal", NORMAL, "global"), ("shift", SHIFT, "global-shift")),
    ),
    "columns-view": (
        "View column",
        layout.SCENE_COLUMN,
        (("normal", NORMAL, "view"), ("shift", SHIFT, "view-shift")),
    ),
    "columns-navigation": (
        "Navigation column",
        layout.NAV_COLUMN,
        (
            ("normal", NORMAL, "navigation"),
            ("shift", SHIFT, "navigation-shift"),
            ("Device/Clip", DEVICE_CLIP_HELD, "device-clip"),
        ),
    ),
}


def figure_svg(slug):
    title, column, panels = FIGURES[slug]
    return draw.figure(
        title,
        [
            draw.panel(engine.render(*scene), [column], section_labels(section), (), caption=caption)
            for caption, scene, section in panels
        ],
    )
