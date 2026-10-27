from BleakLoop.device import SlideDecoder
from BleakLoop.core.model import PadPress, SlideMoved, XAxis


def test_lsb_then_msb_gives_one_x_report():
    decoder = SlideDecoder()
    assert decoder.x_lsb(2, 5, 3) is None
    # Device row 2 is pad 6.
    assert decoder.x_msb(2, 5, 10) == XAxis(5, 6, 10 << 7 | 3)


def test_transfer_gives_one_slide_and_nothing_else():
    decoder = SlideDecoder()
    decoder.transfer(0, 11)
    assert decoder.pad(0, 12, 90) == SlideMoved(8, 11, 12)
    assert decoder.pad(0, 11, 0) is None


def test_source_release_with_target_column_velocity_is_swallowed():
    decoder = SlideDecoder()
    decoder.transfer(3, 4)
    assert decoder.pad(3, 5, 70) == SlideMoved(5, 4, 5)
    assert decoder.pad(3, 4, 5) is None
    # Only once: the next message on the source goes through.
    assert decoder.pad(3, 4, 100) == PadPress(4, 5, True)


def test_plain_press_and_release_pass_through():
    decoder = SlideDecoder()
    assert decoder.pad(7, 2, 100) == PadPress(2, 1, True)
    assert decoder.pad(7, 2, 0) == PadPress(2, 1, False)


def test_release_on_another_column_after_a_transfer_is_not_swallowed():
    decoder = SlideDecoder()
    decoder.transfer(1, 6)
    assert decoder.pad(1, 9, 0) == PadPress(9, 7, False)
    assert decoder.pad(1, 7, 80) == SlideMoved(7, 6, 7)
