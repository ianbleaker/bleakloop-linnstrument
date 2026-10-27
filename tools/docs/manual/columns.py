"""The column figures: one column each, a panel per layer, labelled from its own section."""

from BleakLoop.core import engine, layout

from . import draw
from .pads import section_labels
from .scenes import (
    DEVICE_CLIP_HELD,
    LINNSTRUMENT,
    LINNSTRUMENT_SCENES,
    LINNSTRUMENT_SHIFT,
    SCENES,
    Layer,
)

NORMAL = SCENES[Layer.SESSION]
SHIFT = SCENES[Layer.SESSION_SHIFT]

# slug -> (title, column, panels of (caption, (state, snapshot), section)). A held panel
# with no caption is captioned with its hold.
FIGURES = {
    "columns-global": (
        "Global column",
        1,
        (("normal", NORMAL, "global"), (None, SHIFT, "global-shift")),
    ),
    "columns-view": (
        "View column",
        layout.SCENE_COLUMN,
        (("normal", NORMAL, "view"), (None, SHIFT, "view-shift")),
    ),
    "columns-navigation": (
        "Navigation column",
        layout.NAV_COLUMN,
        (
            ("normal", NORMAL, "navigation"),
            (None, SHIFT, "navigation-shift"),
            (None, DEVICE_CLIP_HELD, "device-clip"),
        ),
    ),
    "linnstrument": (
        "Linnstrument Mode",
        1,
        (
            ("controls", LINNSTRUMENT, "linnstrument"),
            (None, LINNSTRUMENT_SHIFT, "linnstrument-shift"),
            ("scene page", LINNSTRUMENT_SCENES, "linnstrument-scenes"),
        ),
    ),
}


def figure_svg(slug):
    title, column, panels = FIGURES[slug]
    return draw.figure(
        title,
        [
            draw.panel(
                engine.render(*scene),
                [column],
                section_labels(section),
                (),
                caption=caption,
                held=draw.held_of(scene[0]),
            )
            for caption, scene, section in panels
        ],
    )
