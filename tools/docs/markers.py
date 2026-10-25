"""Rewrite generated text between a pair of HTML comment markers."""

import re


class MissingMarkers(Exception):
    def __init__(self, path, start):
        super().__init__(f"{path}: missing markers {start}")
        self.path = path


def replace_between(text, start, end, body, path):
    pattern = re.compile(re.escape(start) + r"\n.*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise MissingMarkers(path, start)
    return pattern.sub(lambda _: f"{start}\n{body}{end}", text, count=1)


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
