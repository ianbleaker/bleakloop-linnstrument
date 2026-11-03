"""Serve the button editor outside Live, for working on the page.

PYTHONPATH=src python3 -m tools.serve_editor USER_FILE [--port N]

Saves go to USER_FILE, never to your User Library's own file, and reload the layout in this
process only.
"""

import sys
import time
from pathlib import Path

from BleakLoop.core import buttons, userfile
from BleakLoop.editor import server


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    user = Path(argv[0]).resolve()
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else userfile.EDITOR["port"]
    buttons.USER_PATH = user
    buttons.reload(buttons.PATH, user)

    def reload():
        try:
            buttons.reload(buttons.PATH, user)
        except ValueError as error:
            return str(error)
        return None

    instance = server.Server(port, server.Editor(port, reload, user_path=user).handle)
    print(f"Editor on http://{server.HOST}:{port}, saving to {user}")
    try:
        while True:
            instance.poll()
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        instance.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
