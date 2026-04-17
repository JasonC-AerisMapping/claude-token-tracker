"""pywebview JS bridge. Only these methods are exposed to JavaScript."""
import csv
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from claude_token_tracker.core.aggregator import (
    VALID_RANGES,
    build_snapshot,
    session_to_dict,
)
from claude_token_tracker.core.parser import IncrementalScanner

__version__ = "2.0.0"


class Api:
    """The only Python surface JavaScript can reach.

    Methods are deliberately few and read-only. ``range`` is whitelist-validated;
    ``project`` and ``session_id`` are matched against currently-known values or
    return empty — never passed to the filesystem directly.
    """

    def __init__(
        self,
        claude_dir: Path,
        now_fn: Callable[[], datetime] | None = None,
        save_dialog_fn: Callable[[str], str | None] | None = None,
        reveal_fn: Callable[[Path], None] | None = None,
    ) -> None:
        self._scanner = IncrementalScanner(root=Path(claude_dir))
        self._claude_dir = Path(claude_dir)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._save_dialog_fn = save_dialog_fn or _default_save_dialog
        self._reveal_fn = reveal_fn or _default_reveal

    # ── Exposed to JS ──

    def get_dashboard(self, range: str = "30d", project: str | None = None) -> dict:
        if range not in VALID_RANGES:
            return {"error": "invalid range"}
        sessions = self._scanner.scan()
        known_projects = {s.project for s in sessions}
        if project and project not in known_projects:
            project = None
        return build_snapshot(sessions, range_=range, now=self._now_fn(), project=project)

    def get_session(self, session_id: str) -> dict:
        for s in self._scanner.scan():
            if s.session_id == session_id:
                return session_to_dict(s)
        return {"error": "not found"}

    def open_session_folder(self, session_id: str) -> bool:
        for s in self._scanner.scan():
            if s.session_id == session_id:
                folder = Path(s.file).parent
                if self._is_within_root(folder):
                    self._reveal_fn(folder)
                    return True
                return False
        return False

    def export_csv(self) -> bool:
        dest = self._save_dialog_fn(f"claude-tokens-{self._now_fn().strftime('%Y-%m-%d')}.csv")
        if not dest:
            return False
        sessions = self._scanner.scan()
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "session_id", "project", "model", "title",
                "first_timestamp", "last_timestamp",
                "input_tokens", "output_tokens",
                "cache_create_tokens", "cache_read_tokens", "total_tokens",
                "is_subagent",
            ])
            for s in sessions:
                w.writerow([
                    s.session_id, s.project, s.model or "", s.title or "",
                    s.first_timestamp.isoformat() if s.first_timestamp else "",
                    s.last_timestamp.isoformat() if s.last_timestamp else "",
                    s.input_tokens, s.output_tokens,
                    s.cache_create_tokens, s.cache_read_tokens, s.total_tokens,
                    s.is_subagent,
                ])
        return True

    def get_app_info(self) -> dict:
        return {
            "version": __version__,
            "data_source": str(self._claude_dir),
        }

    # ── Helpers ──

    def _is_within_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._claude_dir.resolve())
            return True
        except ValueError:
            return False


def _default_save_dialog(suggested_name: str) -> str | None:
    import webview
    if not webview.windows:
        return None
    result = webview.windows[0].create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=suggested_name,
        file_types=("CSV (*.csv)",),
    )
    if not result:
        return None
    return result if isinstance(result, str) else result[0]


def _default_reveal(folder: Path) -> None:
    if sys.platform == "win32":
        os.startfile(folder)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])
