"""Check src/BleakLoop/buttons.toml before restarting Live: prints OK, or what's wrong.

PYTHONPATH=src python3 -m tools.check_buttons [PATH]
"""

import sys
from pathlib import Path

from BleakLoop.core import buttons


def main(argv):
    path = Path(argv[0]) if argv else buttons.PATH
    try:
        buttons.load(path)
    except (ValueError, OSError) as error:  # a bad entry or TOML syntax, or a missing file
        print(f"{path}: {error}", file=sys.stderr)
        return 1
    print(f"{path}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
