"""Generate the manual's and the architecture doc's generated parts, or check they're current.

PYTHONPATH=src python3 -m tools.docs [--check]
"""

import sys
from pathlib import Path

from .architecture import generate as architecture
from .manual import generate as manual
from .markers import MissingMarkers, read

ROOT = Path(__file__).resolve().parents[2]
TARGETS = (manual, architecture)


def expected():
    files = {}
    for target in TARGETS:
        files.update(target.expected())
    return files


def strays():
    return sorted(path for target in TARGETS for path in target.strays())


def write():
    for path, text in expected().items():
        if read(path) != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    for path in strays():
        path.unlink()


def check():
    # Every stale or missing path; nothing is written.
    files = expected()
    return [path for path, text in files.items() if read(path) != text] + strays()


def main(argv):
    try:
        if "--check" not in argv:
            write()
            return 0
        stale = check()
    except MissingMarkers as error:
        print(error)
        if "--check" not in argv:
            return 1
        stale = [error.path]
    for path in stale:
        print(f"stale: {path.relative_to(ROOT)}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
