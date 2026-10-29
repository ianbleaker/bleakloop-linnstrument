import pytest

from BleakLoop.core import harmony
from BleakLoop.core.harmony import Key

C_MAJOR = Key(0)
A_MINOR = Key(9, (0, 2, 3, 5, 7, 8, 10), "Minor")
E_FLAT_MAJOR = Key(3)
C_PENTATONIC = Key(0, (0, 2, 4, 7, 9), "Major Pentatonic")


def degree(key, semitone):
    # The degree row's root for column 3 + semitone, octave 0.
    return 60 + key.root + semitone


def play(key, root, qualities=(), extensions=(), inv=0, spread=0, bass=False):
    chord = harmony.chord(key, root, tuple(qualities), frozenset(extensions))
    voicing = harmony.voice(chord, inv, spread, bass)
    return chord, voicing


def describe(key, root, *a, **k):
    chord, voicing = play(key, root, *a, **k)
    return harmony.describe(key, chord, voicing)


def pitches(key, root, *a, **k):
    chord, voicing = play(key, root, *a, **k)
    return harmony.pitches(key, chord, voicing)


@pytest.mark.parametrize(
    "semitone, quality",
    [(0, "maj"), (2, "min"), (4, "min"), (5, "maj"), (7, "maj"), (9, "min"), (11, "dim")],
)
def test_c_major_degree_row_qualities(semitone, quality):
    assert harmony.chord(C_MAJOR, degree(C_MAJOR, semitone), (), frozenset()).quality == quality


@pytest.mark.parametrize(
    "semitone, name", [(0, "Cmaj7"), (2, "Dm7"), (7, "G7"), (11, "Bm7♭5")]
)
def test_seventh_on_degree_pads(semitone, name):
    assert describe(C_MAJOR, degree(C_MAJOR, semitone), (), {"7"}).startswith(name + " · ")


def test_piano_g_with_maj_and_7():
    assert describe(C_MAJOR, 55, ["maj"], {"7"}).startswith("G7 · V7 in C major · ")


def test_d_with_maj_is_v_of_v():
    assert "V of V" in describe(C_MAJOR, 62, ["maj"])


def test_f_with_min_is_borrowed():
    assert "iv, borrowed from C minor" in describe(C_MAJOR, 65, ["min"])


def test_flat_seven_with_maj_is_borrowed():
    assert describe(C_MAJOR, degree(C_MAJOR, 10), ["maj"]).startswith(
        "B♭ · ♭VII, borrowed from C minor · B♭ D F"
    )


def test_c_with_sus4_is_suspended():
    assert "suspended" in describe(C_MAJOR, 60, ["sus4"])


def test_e_major_in_a_minor_is_from_harmonic_minor():
    assert "from harmonic minor" in describe(A_MINOR, 64, ["maj"])


def test_first_inversion():
    assert pitches(C_MAJOR, 60, inv=1) == (52, 55, 60)


def test_first_inversion_is_a_slash_chord():
    assert describe(C_MAJOR, 60, inv=1).startswith("C/E · ")


def test_open_raises_the_second_lowest():
    assert pitches(C_MAJOR, 60, ["maj"], spread=1) == (60, 67, 76)


def test_wide_with_the_root_lowest_raises_the_rest():
    assert pitches(C_MAJOR, 60, ["maj"], spread=2) == (60, 79, 88)


def test_wide_drops_the_lowest_when_it_isnt_the_root():
    assert pitches(C_MAJOR, 60, ["maj"], inv=1, spread=2) == (40, 60, 67)


def test_bass_adds_the_root_below():
    assert pitches(C_MAJOR, 60, inv=1, bass=True) == (48, 52, 55, 60)


def test_a_13_chord_with_bass_caps_at_seven_notes():
    chord, voicing = play(C_MAJOR, 60, ["maj"], {"7", "9", "11", "13"}, bass=True)
    assert (harmony.pitches(C_MAJOR, chord, voicing), voicing.capped) == (
        (48, 60, 64, 67, 70, 74, 77),
        True,
    )


def test_e_flat_major_names_notes_with_flats():
    assert describe(E_FLAT_MAJOR, 63).startswith("E♭ · I in E♭ major · E♭ G B♭")


def test_pentatonic_with_nothing_held_plays_maj_in_semitones():
    chord, voicing = play(C_PENTATONIC, 62)
    assert (chord.mode, harmony.pitches(C_PENTATONIC, chord, voicing)) == (
        "semitone",
        (62, 66, 69),
    )


def test_maj7_alone_is_maj_and_maj7():
    assert describe(C_MAJOR, 62, (), {"maj7"}).startswith("Dmaj7 · ")


def test_out_of_key_with_nothing_held_is_silent():
    assert harmony.chord(C_MAJOR, 70, (), frozenset()) is None


def test_hint_names_the_borrowed_quality():
    assert harmony.hint(C_MAJOR, 10) == "Hold Maj for ♭VII"


@pytest.mark.parametrize("key", [C_MAJOR, A_MINOR, C_PENTATONIC])
@pytest.mark.parametrize("qualities", [(), ("maj",), ("dim",)])
@pytest.mark.parametrize(
    "extensions", [set(), {"7"}, {"maj7", "9"}, {"7", "9", "11", "13", "6"}]
)
@pytest.mark.parametrize("inv, spread, bass", [(0, 0, False), (3, 2, True), (2, 1, True)])
def test_shifts_stay_in_range(key, qualities, extensions, inv, spread, bass):
    chord, voicing = play(key, 60 + key.root, qualities, extensions, inv, spread, bass)
    values, _ = harmony.shifts(chord, voicing)
    assert len(values) == 6 and all(-36 <= v <= 36 for v in values)
