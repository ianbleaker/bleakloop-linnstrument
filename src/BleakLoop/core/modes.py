"""Modes and the core's state (S-7–S-16)."""

import enum
from dataclasses import dataclass


class Mode(enum.Enum):
    SESSION = enum.auto()
    NOTE = enum.auto()


@dataclass(frozen=True)
class State:
    mode: Mode = Mode.SESSION
