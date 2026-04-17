"""Claude Token Tracker — entrypoint."""
import sys
from pathlib import Path

import webview

from claude_token_tracker.bridge.api import Api

CLAUDE_DIR = Path.home() / ".claude" / "projects"


def _ui_dir() -> Path:
    """Return the path to the bundled ui/ directory.

    Works both in-dev (running from source) and in a PyInstaller one-file exe
    (where assets are extracted to sys._MEIPASS).
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent
    return base / "claude_token_tracker" / "ui"


def main() -> None:
    api = Api(claude_dir=CLAUDE_DIR)
    ui = _ui_dir()
    index = ui / "index.html"
    if not index.exists():
        raise SystemExit(f"UI assets not found at {index}")

    webview.create_window(
        title="Claude Token Tracker",
        url=str(index),
        js_api=api,
        width=1500,
        height=960,
        min_size=(480, 600),
        background_color="#0a0a0f",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
