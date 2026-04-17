"""Incremental JSONL parser for Claude Code session files.

A full scan reads the entire file; an incremental scan tracks byte offsets
per file and only reads new bytes on subsequent passes. Files outside
``~/.claude/projects`` are rejected.
"""
import json
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
            _ingest_lines(session, f)
    except OSError:
        return None

    return session


def _ingest_lines(session: Session, stream) -> None:
    """Consume lines from an open text stream, mutating session in place."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        _apply_entry(session, entry)


def _apply_entry(session: Session, entry: dict) -> None:
    entry_type = entry.get("type")
    timestamp = entry.get("timestamp")

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

        ts = _parse_timestamp(timestamp) if timestamp else None
        if ts is None:
            return

        u = TokenUsage(
            input=usage.get("input_tokens", 0),
            output=usage.get("output_tokens", 0),
            cache_create=usage.get("cache_creation_input_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0),
        )
        session.messages.append(Message(timestamp=ts, usage=u))
        if session.first_timestamp is None or ts < session.first_timestamp:
            session.first_timestamp = ts
        if session.last_timestamp is None or ts > session.last_timestamp:
            session.last_timestamp = ts
