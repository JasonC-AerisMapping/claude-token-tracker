"""Incremental JSONL parser for Claude Code session files.

A full scan reads the entire file; an incremental scan tracks byte offsets
per file and only reads new bytes on subsequent passes. The scanner only
walks ``*.jsonl`` files under the ``root`` it was constructed with — callers
are responsible for pinning that root to ``~/.claude/projects``.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Message, Session, TokenUsage


def _parse_timestamp(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def parse_session_file(
    filepath: Path,
    project: str,
    is_subagent: bool = False,
) -> Optional[Session]:
    """Full parse of a JSONL file. Returns None if file cannot be opened."""
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    session = Session(
        file=str(filepath),
        project=project,
        session_id=filepath.stem,
        title=None,
        model=None,
        is_subagent=is_subagent,
    )

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            _ingest_lines(session, f, {})
    except OSError:
        return None

    return session


def _ingest_lines(session: Session, stream, msg_index: dict[str, int]) -> None:
    """Consume lines from an open text stream, mutating session in place.

    ``msg_index`` maps message.id -> position in session.messages and must
    persist across incremental reads of the same file (see IncrementalScanner).
    """
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        _apply_entry(session, entry, msg_index)


def _apply_entry(session: Session, entry: dict, msg_index: dict[str, int]) -> None:
    entry_type = entry.get("type")
    timestamp = entry.get("timestamp")

    if session.cwd is None and entry.get("cwd"):
        session.cwd = entry["cwd"]

    if entry_type == "ai-title":
        session.title = entry.get("aiTitle")
        return

    if entry_type == "assistant":
        msg = entry.get("message") or {}
        usage = msg.get("usage") or {}
        if not usage:
            return
        if not session.model:
            session.model = msg.get("model")

        # Usage on a timestamp-less line would be dropped here. Audited against
        # the full corpus 2026-07-10: zero such lines exist in real logs.
        ts = _parse_timestamp(timestamp) if timestamp else None
        if ts is None:
            return

        u = TokenUsage(
            input=usage.get("input_tokens", 0),
            output=usage.get("output_tokens", 0),
            cache_create=usage.get("cache_creation_input_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0),
            cache_create_1h=(usage.get("cache_creation") or {}).get(
                "ephemeral_1h_input_tokens", 0
            ),
        )
        model = msg.get("model")

        # One API call is logged once per content block, every line repeating
        # the call's usage — and mid-stream lines carry a placeholder output
        # count. Counting each line multiplies real usage ~2.5x. Keep exactly
        # one Message per message.id, always with the latest (final) usage.
        # The model can flip mid-call (server-side fallback), so the latest
        # line's model wins too — that's the model that produced the billing.
        mid = msg.get("id")
        if mid is not None:
            pos = msg_index.get(mid)
            if pos is not None:
                old = session.messages[pos]
                session.messages[pos] = Message(
                    timestamp=old.timestamp, usage=u, model=model or old.model
                )
                return
            msg_index[mid] = len(session.messages)

        session.messages.append(Message(timestamp=ts, usage=u, model=model))
        if session.first_timestamp is None or ts < session.first_timestamp:
            session.first_timestamp = ts
        if session.last_timestamp is None or ts > session.last_timestamp:
            session.last_timestamp = ts


@dataclass(slots=True)
class _FileState:
    offset: int
    mtime: float
    session: Session
    # message.id -> index in session.messages; must survive between scans so a
    # usage-finalizing line in a later chunk updates rather than duplicates.
    msg_index: dict[str, int]


class IncrementalScanner:
    """Scans a directory tree for .jsonl session files, parsing incrementally.

    Keeps ``(offset, mtime, session)`` per file. On each ``scan()``:
      * New files get a full parse.
      * Unchanged files return their cached session object.
      * Grown files seek to the last offset and ingest only new bytes.
      * Deleted files are evicted from the cache.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._state: dict[Path, _FileState] = {}

    def scan(self) -> list[Session]:
        if not self._root.exists():
            self._state.clear()
            return []

        seen: set[Path] = set()
        for jsonl in self._root.rglob("*.jsonl"):
            if not jsonl.is_file():
                continue
            seen.add(jsonl)
            self._scan_one(jsonl)

        # Evict deleted files
        for stale in list(self._state.keys()):
            if stale not in seen:
                del self._state[stale]

        return [st.session for st in self._state.values()]

    def _scan_one(self, filepath: Path) -> None:
        try:
            stat = filepath.stat()
        except OSError:
            return

        state = self._state.get(filepath)
        if state is not None and state.mtime == stat.st_mtime and state.offset == stat.st_size:
            return  # unchanged

        project = self._project_from_path(filepath)
        is_subagent = _detect_subagent(filepath, self._root)

        if state is None:
            # New file → full parse + record offset
            session = Session(
                file=str(filepath),
                project=project,
                session_id=filepath.stem,
                title=None,
                model=None,
                is_subagent=is_subagent,
            )
            msg_index: dict[str, int] = {}
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    _ingest_lines(session, f, msg_index)
                    new_offset = f.tell()
            except OSError:
                return
            self._state[filepath] = _FileState(
                offset=new_offset, mtime=stat.st_mtime, session=session,
                msg_index=msg_index,
            )
            return

        # Existing file, grown or rewritten
        if stat.st_size < state.offset:
            # File truncated / rewritten → full re-parse
            state.session.messages.clear()
            state.session.title = None
            state.session.model = None
            state.session.first_timestamp = None
            state.session.last_timestamp = None
            state.session.cwd = None
            state.msg_index.clear()
            state.offset = 0

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                f.seek(state.offset)
                _ingest_lines(state.session, f, state.msg_index)
                state.offset = f.tell()
        except OSError:
            return
        state.mtime = stat.st_mtime

    def _project_from_path(self, filepath: Path) -> str:
        # The parent directory name under root is the project-dir identifier.
        try:
            rel = filepath.relative_to(self._root)
        except ValueError:
            return "unknown"
        parts = rel.parts
        return decode_project_name(parts[0]) if parts else "unknown"


def decode_project_name(dir_name: str) -> str:
    """Take the last '--'-separated component and replace '-' with '/'.

    No user-specific prefix stripping — we want this to work on any machine.
    """
    if not dir_name:
        return "unknown"
    parts = dir_name.split("--")
    return parts[-1].replace("-", "/") if len(parts) > 1 else dir_name


def _detect_subagent(filepath: Path, root: Path) -> bool:
    """A file is a subagent if it lives in a subdirectory *inside* the project dir."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        return False
    # rel.parts[0] is the project dir; a direct child is non-subagent,
    # anything deeper is a subagent.
    return len(rel.parts) > 2 and "memory" not in rel.parts
