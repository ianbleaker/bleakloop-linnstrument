"""Check src/BleakLoop/buttons.toml, or it with a user's buttons file over it: prints OK, or
what's wrong.

PYTHONPATH=src python3 -m tools.check_buttons [PATH] [--user USER_PATH]
"""

import sys
from pathlib import Path

from BleakLoop.core import buttons


def main(argv):
    argv = list(argv)
    user = None
    if "--user" in argv:
        at = argv.index("--user")
        if at + 1 >= len(argv):
            print(__doc__.strip(), file=sys.stderr)
            return 2
        user = Path(argv[at + 1])
        del argv[at : at + 2]
        if not user.exists():
            print(f"{user}: no such file", file=sys.stderr)
            return 1
    path = Path(argv[0]) if argv else buttons.PATH
    try:
        buttons.load(path, user)
    except (ValueError, OSError) as error:  # a bad entry or TOML syntax, or a missing file
        text = str(error)
        print(text if user and text.startswith(str(user)) else f"{path}: {text}", file=sys.stderr)
        return 1
    print(f"{path}{f' with {user}' if user else ''}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
