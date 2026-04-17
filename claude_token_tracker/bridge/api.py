"""pywebview JS bridge. Only these methods are exposed to JavaScript."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from claude_token_tracker.core.aggregator import VALID_RANGES, build_snapshot
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
    ) -> None:
        self._scanner = IncrementalScanner(root=Path(claude_dir))
        self._claude_dir = Path(claude_dir)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    # ── Exposed to JS ──

    def get_dashboard(self, range: str = "30d", project: str | None = None) -> dict:
        if range not in VALID_RANGES:
            return {"error": "invalid range"}
        sessions = self._scanner.scan()
        known_projects = {s.project for s in sessions}
        if project and project not in known_projects:
            project = None  # silently drop unknown filter values
        return build_snapshot(sessions, range_=range, now=self._now_fn(), project=project)

    def get_session(self, session_id: str) -> dict:
        for s in self._scanner.scan():
            if s.session_id == session_id:
                from claude_token_tracker.core.aggregator import _session_to_dict
                return _session_to_dict(s)
        return {"error": "not found"}

    def get_app_info(self) -> dict:
        return {
            "version": __version__,
            "data_source": str(self._claude_dir),
        }
