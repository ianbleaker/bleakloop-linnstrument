"""Chord Mode's theory: chords, voicings, the Chord device's shifts and the status line.

Pure: no Live. A chord's tones are offsets from its root in "units": semitones in semitone
mode, scale degrees in scale mode, where Live's Chord device follows the Set's scale (Use
Current Scale). The root is always at offset 0: it's the note the pad is translated to.
"""

from dataclasses import dataclass

from .leds import BLUE, MAGENTA, ORANGE, PINK, RED

MAX_NOTES = 7  # the incoming note and the Chord device's 6 shifts
SHIFTS = MAX_NOTES - 1
SHIFT_RANGE = 36

# Third and fifth in semitones, the pad's label and colour.
QUALITIES = {
    "maj": (4, 7, "Maj", ORANGE),
    "min": (3, 7, "Min", BLUE),
    "sus4": (5, 7, "Sus4", PINK),
    "sus2": (2, 7, "Sus2", PINK),
    "dim": (3, 6, "Dim", RED),
    "aug": (4, 8, "Aug", MAGENTA),
}
# Role, scale-degree steps (None: no scale-degree form) and semitones. In stacking order:
# maj7 before 7, so maj7 wins the "7" role.
EXTENSIONS = {
    "6": ("6", 5, 9),
    "maj7": ("7", None, 11),
    "7": ("7", 6, 10),
    "9": ("9", 8, 14),
    "11": ("11", 10, 17),
    "13": ("13", 12, 21),
}
# An out-of-key semitone above the key root: (roman letter index, accidental, quality, what
# it does), by the key's third-degree shape.
BORROWED_MAJOR = {
    1: (1, "♭", "maj", "the Neapolitan"),
    3: (2, "♭", "maj", "borrowed from {} minor"),
    6: (3, "♯", "dim", "leads to V"),
    8: (5, "♭", "maj", "borrowed from {} minor"),
    10: (6, "♭", "maj", "borrowed from {} minor"),
}
BORROWED_MINOR = {
    1: (1, "♭", "maj", "the Neapolitan"),
    4: (2, "", "min", "borrowed from {} major"),
    6: (3, "♯", "dim", "leads to V"),
    9: (5, "", "min", "borrowed from {} major"),
    11: (6, "", "dim", "from harmonic minor"),
}
# The piano, by column - 6: pad pairs' naturals and sharps, None a dark gap.
WHITES = (0, 2, 4, 5, 7, 9, 11, 12, 14)
BLACKS = (1, 3, None, 6, 8, 10, None, 13, None)

MAJOR = (0, 2, 4, 5, 7, 9, 11)
SHARPS = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
FLATS = ("C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B")
ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII")
INVERSIONS = ("Root", "1st", "2nd", "3rd")
SPREADS = ("Close", "Open", "Wide")
SEMI_NAMES = {13: "♭9", 14: "9", 15: "♯9", 16: "♭11", 17: "11", 18: "♯11", 20: "♭13", 21: "13"}
QUALITY_WORDS = {"maj": "major", "min": "minor", "dim": "diminished", "aug": "augmented"}


@dataclass(frozen=True)
class Key:
    root: int  # pitch class
    intervals: tuple = MAJOR  # Song.scale_intervals
    name: str = "Major"  # Song.scale_name

    @property
    def is_heptatonic(self):
        return len(self.intervals) == 7

    @property
    def is_minor(self):
        # The third degree's shape: 3 semitones is minor-shaped.
        return self.is_heptatonic and self.intervals[2] == 3

    @property
    def uses_flats(self):
        return self.root in (5, 10, 3, 8, 1) or (self.is_minor and self.root in (2, 7, 0, 5))

    @property
    def text(self):
        return f"{self.note_name(self.root)} {self.name.lower()}"

    def note_name(self, note, flats=None):
        flats = self.uses_flats if flats is None else flats
        return (FLATS if flats else SHARPS)[note % 12]

    def degree_of(self, pc):
        # The index in the scale of an absolute pitch class, or None.
        semitone = (pc - self.root) % 12
        return self.intervals.index(semitone) if semitone in self.intervals else None

    def step(self, i):
        # Semitones from the key root to scale step i, which may be negative or past 7.
        n = len(self.intervals)
        return self.intervals[i % n] + 12 * (i // n)

    def diatonic_quality(self, d):
        third, fifth = self.step(d + 2) - self.step(d), self.step(d + 4) - self.step(d)
        for quality in ("maj", "min", "dim"):
            if QUALITIES[quality][:2] == (third, fifth):
                return quality
        return "aug"

    def borrowed(self, semitone):
        # The borrowed entry for an out-of-key semitone: the shape's table, then the other's.
        first, second = (BORROWED_MINOR, BORROWED_MAJOR)
        if not self.is_minor:
            first, second = second, first
        return first.get(semitone) or second.get(semitone) or (semitone * 7 // 12, "", "maj", "")

    def borrowed_quality(self, semitone):
        return self.borrowed(semitone)[2]


@dataclass(frozen=True)
class Chord:
    root: int  # MIDI note
    mode: str  # "scale" or "semitone"
    quality: str
    tones: tuple  # (offset, role) per tone, ascending, the root first
    degree: int | None = None  # the root's index in the key, None outside it


@dataclass(frozen=True)
class Voicing:
    offsets: tuple  # in the chord's units, ascending, the root at 0 included
    capped: bool = False
    inv: int = 0
    spread: int = 0
    bass: bool = False


# Chords


def shape(key, qualities, extensions):
    # The chord shape a press gets now, before its root is known: (mode, quality, tones).
    # quality is None in scale mode, where each degree gets its own.
    held = qualities[-1] if qualities else None
    if held is None and key.is_heptatonic and "maj7" not in extensions:
        tones = [(0, "R"), (2, "3"), (4, "5")]
        for name, (role, steps, _) in EXTENSIONS.items():
            if name in extensions and steps is not None:
                _add(tones, steps, role)
        return "scale", None, tuple(tones)
    # A held quality; maj7 alone, which has no scale-degree form; or a scale without 7
    # notes: Maj.
    quality = held or "maj"
    third, fifth = QUALITIES[quality][:2]
    tones = [(0, "R"), (third, "3"), (fifth, "5")]
    for name, (role, _, semitones) in EXTENSIONS.items():
        if name in extensions:
            _add(tones, semitones, role)
    return "semitone", quality, tuple(tones)


def _add(tones, offset, role):
    if all(r != role for _, r in tones):
        tones.append((offset, role))


def chord(key, root_note, qualities, extensions):
    # None for a silent press: outside the key, or the scale, with no quality held.
    d = key.degree_of(root_note % 12)
    if d is None and not qualities:
        return None
    mode, quality, tones = shape(key, qualities, extensions)
    if quality is None:
        quality = key.diatonic_quality(d)
    return Chord(root_note, mode, quality, tuple(sorted(tones)), d)


def hint(key, semitone):
    # For a silent press on an out-of-key semitone.
    if not key.is_heptatonic:
        return f"Hold a quality to play {key.note_name(key.root + semitone)}"
    quality = key.borrowed_quality(semitone)
    return f"Hold {QUALITIES[quality][2]} for {_borrowed_roman(key, semitone)}"


# Voicing


def voice(chord, inv, spread, bass):
    unit = 7 if chord.mode == "scale" else 12
    tones = [offset for offset, _ in chord.tones]
    inv %= len(tones)
    # Inversion k drops every tone from index k down an octave; the root stays at 0.
    notes = sorted(t - unit if inv and i >= inv else t for i, t in enumerate(tones))
    if spread >= 1:
        _raise(notes, 1, unit)
    if spread >= 2:
        _raise(notes, 3, unit)
        # The lowest drops an octave; when it's the root, which stays at 0, the rest rise.
        if notes[0] != 0:
            notes[0] -= unit
        else:
            notes = [n + unit if n else n for n in notes]
        notes.sort()
    if bass:
        low = -unit
        while low >= notes[0]:
            low -= unit
        notes.insert(0, low)
    merged = sorted(set(notes))
    notes = [n for n in merged if -SHIFT_RANGE <= n <= SHIFT_RANGE]
    capped = len(notes) < len(merged) or len(notes) > MAX_NOTES
    while len(notes) > MAX_NOTES:
        notes.remove(max(n for n in notes if n != 0))
    return Voicing(tuple(notes), capped, inv, spread, bass)


def _raise(notes, index, unit):
    # Up an octave: the note at index, or the next one up if that's the root.
    candidates = [i for i in range(index, len(notes)) if notes[i] != 0]
    if index < len(notes) and candidates:
        notes[candidates[0]] += unit
        notes.sort()


def pitches(key, chord, voicing):
    # Absolute MIDI notes, as the Chord device plays them.
    if chord.mode == "semitone":
        return tuple(chord.root + o for o in voicing.offsets)
    d = chord.degree
    return tuple(chord.root + key.step(d + o) - key.step(d) for o in voicing.offsets)


def shifts(chord, voicing):
    # The Chord device's six shifts, unused ones 0, and whether they're scale degrees.
    used = [o for o in voicing.offsets if o != 0]
    return tuple(used + [0] * (SHIFTS - len(used))), chord.mode == "scale"


# The status line


def semitones(key, chord):
    # (semitones, role) per tone: a scale-mode chord's degrees in the key.
    if chord.mode == "semitone":
        return chord.tones
    d = chord.degree
    return tuple((key.step(d + o) - key.step(d), role) for o, role in chord.tones)


def describe(key, chord, voicing):
    tones = semitones(key, chord)
    notes = pitches(key, chord, voicing)
    # A chord borrowed on a flat degree is spelled with flats: B♭ for ♭VII in C major.
    flats = key.uses_flats
    if chord.degree is None and key.is_heptatonic:
        flats = flats or key.borrowed((chord.root - key.root) % 12)[1] == "♭"

    def spell(note):
        return key.note_name(note, flats)

    name = chord_name(spell, chord.root, chord.quality, tones)
    if notes[0] % 12 != chord.root % 12:
        name += "/" + spell(notes[0])
    parts = [name, explain(key, chord, tones), " ".join(spell(n) for n in notes)]
    if voicing.inv or voicing.spread or voicing.bass:
        text = f"{INVERSIONS[voicing.inv]} inversion, {SPREADS[voicing.spread].lower()}"
        parts.append(text + (", bass" if voicing.bass else ""))
    outside = []
    for n in notes:
        if key.degree_of(n % 12) is None and spell(n) not in outside:
            outside.append(spell(n))
    if outside:
        parts.append(f"{', '.join(outside)} {'are' if len(outside) > 1 else 'is'} outside the key")
    if voicing.capped:
        parts.append(f"{MAX_NOTES} notes at most: the highest dropped")
    return " · ".join(parts)


def chord_name(spell, root, quality, tones):
    by_role = {role: s for s, role in tones}
    s7, s6 = by_role.get("7"), by_role.get("6")
    tensions = [SEMI_NAMES.get(by_role[r], r) for r in ("9", "11", "13") if r in by_role]
    q = {"maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus4": "sus4", "sus2": "sus2"}
    seventh = {11: "maj7", 10: "7"}.get(s7, "")
    if quality == "dim" and s7 == 10:
        core = "m7♭5"
    elif quality == "min" and s7 == 11:
        core = "m(maj7)"
    elif quality == "aug" and s7 == 11:
        core = "maj7♯5"
    elif quality == "aug" and s7 == 10:
        core = "aug7"
    elif quality.startswith("sus"):
        core = seventh + q[quality]
    else:
        core = q[quality] + seventh
    if s6 is not None:
        six = "♭6" if s6 == 8 else "6"
        if seventh:
            tensions.append("13" if s6 == 9 else "♭13")
        elif quality in ("maj", "min"):
            core += six
        else:
            core += f"(add{six})"
    if tensions:
        if seventh and tensions == ["9"] and "7" in core:
            core = core.replace("7", "9")
        elif seventh:
            core += f"({','.join(tensions)})"
        elif core.endswith("6") and tensions == ["9"]:
            core += "/9"
        else:
            core += f"(add{','.join(tensions)})"
    return spell(root) + core


def explain(key, chord, tones):
    # The Roman numeral and what the chord does in the key.
    key_text = key.text
    if not key.is_heptatonic:
        inside = "in" if chord.degree is not None else "outside"
        return f"root {inside} {key_text}"
    s7 = dict((role, s) for s, role in tones).get("7")
    quality = chord.quality
    d = chord.degree
    if d is None:
        semitone = (chord.root - key.root) % 12
        letter, accidental, borrowed_quality, does = key.borrowed(semitone)
        roman = _roman(letter, accidental, quality, s7)
        if quality != borrowed_quality or not does:
            return f"{roman}, altered"
        return f"{roman}, {does.format(key.note_name(key.root))}"
    diatonic = key.diatonic_quality(d)
    roman = _roman(d, _accidental(key, d), quality, s7)
    if quality == diatonic:
        return f"{roman} in {key_text}"
    if key.is_minor and d == 4 and quality == "maj":
        return f"{roman}, from harmonic minor"
    if not key.is_minor and d == 3 and quality == "min":
        return f"{roman}, borrowed from {key.note_name(key.root)} minor"
    if quality == "maj" and diatonic in ("min", "dim"):
        target = (d + 3) % 7
        base = _roman(target, _accidental(key, target), key.diatonic_quality(target), None)
        return f"{roman}: V of {base}"
    if quality.startswith("sus") and diatonic != "dim":
        return f"{roman} in {key_text}, suspended"
    base = _roman(d, _accidental(key, d), diatonic, None)
    return f"{roman}, altered: {base} is {QUALITY_WORDS[diatonic]} in {key_text}"


def _accidental(key, d):
    # Against the major scale: ♭III in a minor key.
    semitone = key.intervals[d]
    return "♭" if semitone < MAJOR[d] else "♯" if semitone > MAJOR[d] else ""


def _borrowed_roman(key, semitone):
    letter, accidental, quality, _ = key.borrowed(semitone)
    return _roman(letter, accidental, quality, None)


def _roman(d, accidental, quality, s7):
    r = ROMANS[d]
    if quality == "min":
        r = r.lower()
    elif quality == "dim":
        r = r.lower() + "°"
    elif quality == "aug":
        r += "+"
    elif quality.startswith("sus"):
        r += quality
    if s7 == 10 and quality == "dim":
        r = r.replace("°", "ø7")
    elif s7 == 11:
        r += "maj7"
    elif s7 == 10 and quality.startswith("sus"):
        r = r.replace(quality, "7" + quality)
    elif s7 == 10:
        r += "7"
    return accidental + r
