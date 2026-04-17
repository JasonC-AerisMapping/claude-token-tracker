# Claude Token Tracker v2 Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Claude Token Tracker desktop app with a glassmorphism HTML/CSS UI in a `pywebview` window, a layered testable Python core with incremental JSONL parsing, and new derived metrics (cache savings, streak, peak hour, activity heatmap).

**Architecture:** Pure-Python `core/` module (parser, aggregator, pricing) with no UI imports; a narrow `bridge/api.py` exposing whitelisted read-only methods to JS; a single-page `ui/` (`index.html` + `styles.css` + `app.js`) using Alpine.js and ECharts, bundled locally. One `app.py` entrypoint wires it together. Packaging via PyInstaller → single `.exe`, installer via existing Inno Setup.

**Tech Stack:** Python 3.14, pywebview, Alpine.js (bundled), ECharts (bundled), pytest, PyInstaller.

**Source of visual truth:** `.superpowers/brainstorm/1965-1776461738/content/dashboard-v1.html` (committed mockup). Treat it as the canonical reference for every CSS class, gradient, and layout decision. When in doubt, open it in a browser and copy.

**Spec reference:** [`docs/superpowers/specs/2026-04-17-token-tracker-redesign-design.md`](../specs/2026-04-17-token-tracker-redesign-design.md)

---

## File Structure

```
claude-token-tracker/
├── app.py                                # NEW entrypoint
├── claude_token_tracker/                 # NEW package
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                     # dataclasses
│   │   ├── pricing.py                    # per-model token prices
│   │   ├── parser.py                     # incremental JSONL reader
│   │   └── aggregator.py                 # rollups + derived metrics
│   ├── bridge/
│   │   ├── __init__.py
│   │   └── api.py                        # pywebview JS bridge
│   └── ui/
│       ├── index.html
│       ├── styles.css
│       ├── app.js
│       └── vendor/
│           ├── alpine.min.js             # pulled from CDN, bundled
│           └── echarts.min.js            # pulled from CDN, bundled
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── session_basic.jsonl
│   │   └── session_incremental.jsonl
│   ├── test_models.py
│   ├── test_pricing.py
│   ├── test_parser.py
│   └── test_aggregator.py
├── requirements.txt                      # UPDATED
├── ClaudeTokenTracker.spec               # UPDATED (bundle ui/)
├── run_tracker.bat                       # UPDATED (new deps)
├── installer.iss                         # unchanged
├── claude_token_tracker.py               # DELETED at the end
└── .gitignore                            # unchanged
```

---

## Task 1: Project skeleton + dependencies

**Files:**
- Create: `claude_token_tracker/__init__.py`
- Create: `claude_token_tracker/core/__init__.py`
- Create: `claude_token_tracker/bridge/__init__.py`
- Create: `claude_token_tracker/ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`
- Modify: `run_tracker.bat`

- [ ] **Step 1: Create empty `__init__.py` files**

Create these five files, each containing exactly one line:

`claude_token_tracker/__init__.py`:
```python
"""Claude Token Tracker — live desktop dashboard for Claude Code token usage."""
```

`claude_token_tracker/core/__init__.py`:
```python
"""Pure-Python data layer. No UI, no pywebview imports allowed."""
```

`claude_token_tracker/bridge/__init__.py`:
```python
"""pywebview JS bridge — the only surface JS can call."""
```

`claude_token_tracker/ui/__init__.py`:
```python
"""Frontend assets (HTML/CSS/JS) bundled via PyInstaller datas."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 2: Create `tests/conftest.py` with shared fixtures dir**

```python
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
```

- [ ] **Step 3: Update `requirements.txt`**

Replace the entire contents with:
```
pywebview
pytest
pyinstaller
```

(`customtkinter` and `matplotlib` are removed.)

- [ ] **Step 4: Update `run_tracker.bat`**

Replace the entire contents with:
```bat
@echo off
title Claude Token Tracker
cd /d "%~dp0"

echo Using Python: C:\Python314\python.exe
"C:\Python314\python.exe" -c "import webview; print('pywebview OK')"
if errorlevel 1 (
    echo.
    echo Installing dependencies...
    "C:\Python314\python.exe" -m pip install -r requirements.txt
)
echo.
echo Launching Claude Token Tracker...
"C:\Python314\python.exe" app.py
pause
```

- [ ] **Step 5: Install new deps and verify imports**

Run:
```bash
python -m pip install -r requirements.txt
python -c "import webview; import pytest; print('ok')"
```
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add claude_token_tracker/ tests/__init__.py tests/conftest.py requirements.txt run_tracker.bat
git commit -m "scaffold v2 package layout and deps"
```

---

## Task 2: Data models

**Files:**
- Create: `claude_token_tracker/core/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime, timezone

from claude_token_tracker.core.models import Message, Session, TokenUsage


def test_token_usage_sums():
    u = TokenUsage(input=10, output=20, cache_create=5, cache_read=100)
    assert u.total == 135


def test_token_usage_zero_default():
    u = TokenUsage()
    assert u.total == 0


def test_session_total_tokens_matches_usage():
    now = datetime.now(timezone.utc)
    s = Session(
        file="/tmp/x.jsonl",
        project="demo",
        session_id="abc",
        title=None,
        model="opus-4.7",
        is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=1, output=2, cache_create=3, cache_read=4)),
            Message(timestamp=now, usage=TokenUsage(input=10, output=20, cache_create=30, cache_read=40)),
        ],
        first_timestamp=now,
        last_timestamp=now,
    )
    assert s.total_tokens == (1 + 2 + 3 + 4) + (10 + 20 + 30 + 40)


def test_session_input_tokens_aggregates():
    now = datetime.now(timezone.utc)
    s = Session(
        file="/tmp/x.jsonl",
        project="demo",
        session_id="abc",
        title=None,
        model=None,
        is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=1)),
            Message(timestamp=now, usage=TokenUsage(input=2)),
        ],
        first_timestamp=now,
        last_timestamp=now,
    )
    assert s.input_tokens == 3
```

- [ ] **Step 2: Run the test — expect import failure**

```bash
python -m pytest tests/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'claude_token_tracker.core.models'`

- [ ] **Step 3: Write the implementation**

`claude_token_tracker/core/models.py`:
```python
"""Dataclasses for session, message, token usage, and dashboard snapshots."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input: int = 0
    output: int = 0
    cache_create: int = 0
    cache_read: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_create + self.cache_read


@dataclass(frozen=True, slots=True)
class Message:
    timestamp: datetime
    usage: TokenUsage


@dataclass(slots=True)
class Session:
    file: str
    project: str
    session_id: str
    title: Optional[str]
    model: Optional[str]
    is_subagent: bool
    messages: list[Message] = field(default_factory=list)
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None

    @property
    def input_tokens(self) -> int:
        return sum(m.usage.input for m in self.messages)

    @property
    def output_tokens(self) -> int:
        return sum(m.usage.output for m in self.messages)

    @property
    def cache_create_tokens(self) -> int:
        return sum(m.usage.cache_create for m in self.messages)

    @property
    def cache_read_tokens(self) -> int:
        return sum(m.usage.cache_read for m in self.messages)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_create_tokens
            + self.cache_read_tokens
        )
```

- [ ] **Step 4: Run the test — expect pass**

```bash
python -m pytest tests/test_models.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/models.py tests/test_models.py
git commit -m "core: add Session / Message / TokenUsage dataclasses"
```

---

## Task 3: Pricing module

**Files:**
- Create: `claude_token_tracker/core/pricing.py`
- Create: `tests/test_pricing.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pricing.py`:
```python
from claude_token_tracker.core.pricing import (
    cache_savings_usd,
    is_known_model,
    normalize_model,
)


def test_normalize_strips_claude_prefix_and_date_suffix():
    assert normalize_model("claude-opus-4-7") == "opus-4-7"
    assert normalize_model("claude-sonnet-4-6-20251001") == "sonnet-4-6"
    assert normalize_model("claude-haiku-4-5-20251001") == "haiku-4-5"


def test_normalize_none_returns_unknown():
    assert normalize_model(None) == "unknown"
    assert normalize_model("") == "unknown"


def test_is_known_model_true_for_known():
    assert is_known_model("claude-opus-4-7")
    assert is_known_model("opus-4-7")


def test_is_known_model_false_for_unknown():
    assert not is_known_model("future-model-9000")
    assert not is_known_model(None)


def test_cache_savings_zero_when_no_cache_read():
    # Input-only, no cache hits → no savings
    assert cache_savings_usd("opus-4-7", cache_read_tokens=0) == 0.0


def test_cache_savings_returns_positive_for_known_model():
    # 1M cache_read tokens should yield a sensible positive dollar value
    savings = cache_savings_usd("opus-4-7", cache_read_tokens=1_000_000)
    assert savings > 0
    assert savings < 20  # sanity — way less than $20 for 1M tokens


def test_cache_savings_zero_for_unknown_model():
    # We underreport rather than guess
    assert cache_savings_usd("future-model-9000", cache_read_tokens=1_000_000) == 0.0
```

- [ ] **Step 2: Run the test — expect failure**

```bash
python -m pytest tests/test_pricing.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`claude_token_tracker/core/pricing.py`:
```python
"""Per-model token pricing and cache-savings calculation.

Prices are USD per 1M tokens, sourced from Anthropic's public pricing page.
Unknown models are excluded from cache-savings totals — we underreport
rather than guess.
"""
from typing import Optional

# Price per 1M tokens in USD. Keys are the normalized model name.
# Update this table when Anthropic publishes new pricing.
PRICING: dict[str, dict[str, float]] = {
    "opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
}


def normalize_model(model: Optional[str]) -> str:
    """Strip 'claude-' prefix and any '-YYYYMMDD' date suffix."""
    if not model:
        return "unknown"
    name = model.removeprefix("claude-")
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        name = parts[0]
    return name


def is_known_model(model: Optional[str]) -> bool:
    return normalize_model(model) in PRICING


def cache_savings_usd(model: Optional[str], cache_read_tokens: int) -> float:
    """USD saved by using cache_read instead of regular input pricing.

    Returns 0.0 for unknown models (we underreport rather than guess).
    """
    key = normalize_model(model)
    if key not in PRICING:
        return 0.0
    prices = PRICING[key]
    full_cost = (cache_read_tokens / 1_000_000) * prices["input"]
    actual_cost = (cache_read_tokens / 1_000_000) * prices["cache_read"]
    return full_cost - actual_cost
```

- [ ] **Step 4: Run the test — expect pass**

```bash
python -m pytest tests/test_pricing.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/pricing.py tests/test_pricing.py
git commit -m "core: add pricing table and cache-savings calculation"
```

---

## Task 4: Parser — full scan of a single file

**Files:**
- Create: `claude_token_tracker/core/parser.py`
- Create: `tests/fixtures/session_basic.jsonl`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Create test fixture**

`tests/fixtures/session_basic.jsonl`:
```
{"type":"ai-title","aiTitle":"Test session title"}
{"type":"user","timestamp":"2026-04-15T10:00:00Z","entrypoint":"cli"}
{"type":"assistant","timestamp":"2026-04-15T10:00:05Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":100,"output_tokens":50,"cache_creation_input_tokens":200,"cache_read_input_tokens":500}}}
{"type":"assistant","timestamp":"2026-04-15T10:05:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":80,"output_tokens":40,"cache_creation_input_tokens":0,"cache_read_input_tokens":700}}}
```

(Exactly 4 lines, each a complete JSON object. No trailing newline is fine.)

- [ ] **Step 2: Write the failing test**

`tests/test_parser.py`:
```python
from claude_token_tracker.core.parser import parse_session_file


def test_parse_basic_session_file(fixtures_dir):
    session = parse_session_file(fixtures_dir / "session_basic.jsonl", project="demo")
    assert session is not None
    assert session.project == "demo"
    assert session.title == "Test session title"
    assert session.model == "claude-opus-4-7"
    assert len(session.messages) == 2
    assert session.input_tokens == 180
    assert session.output_tokens == 90
    assert session.cache_create_tokens == 200
    assert session.cache_read_tokens == 1200
    assert session.total_tokens == 180 + 90 + 200 + 1200


def test_parse_returns_none_for_nonexistent_file(tmp_path):
    assert parse_session_file(tmp_path / "does-not-exist.jsonl", project="x") is None


def test_parse_skips_malformed_json_lines(tmp_path):
    f = tmp_path / "broken.jsonl"
    f.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":10,"output_tokens":5}}}\n'
        'this is not json\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:01:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":20,"output_tokens":10}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert session is not None
    assert len(session.messages) == 2
    assert session.input_tokens == 30
```

- [ ] **Step 3: Run — expect failure**

```bash
python -m pytest tests/test_parser.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Write the minimal implementation**

`claude_token_tracker/core/parser.py`:
```python
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
```

- [ ] **Step 5: Run — expect pass**

```bash
python -m pytest tests/test_parser.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add claude_token_tracker/core/parser.py tests/fixtures/session_basic.jsonl tests/test_parser.py
git commit -m "core: add JSONL session parser (full-scan)"
```

---

## Task 5: Parser — incremental scanner

**Files:**
- Modify: `claude_token_tracker/core/parser.py`
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Add failing tests for incremental behavior**

Append to `tests/test_parser.py`:
```python
from claude_token_tracker.core.parser import IncrementalScanner


def test_incremental_scanner_initial_scan_parses_all(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    sessions = scanner.scan()
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 180


def test_incremental_scanner_rescan_without_changes_is_noop(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    first = scanner.scan()
    second = scanner.scan()
    # Same objects returned from cache
    assert first[0] is second[0]


def test_incremental_scanner_only_reads_new_bytes(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    scanner.scan()

    # Append one more assistant message worth 5 input tokens
    with open(dst, "a", encoding="utf-8") as f:
        f.write('\n{"type":"assistant","timestamp":"2026-04-15T10:10:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":5,"output_tokens":3}}}\n')

    sessions = scanner.scan()
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 185
    assert sessions[0].output_tokens == 93
    assert len(sessions[0].messages) == 3


def test_incremental_scanner_path_whitelist(tmp_path):
    # root doesn't exist → empty scan, no error
    scanner = IncrementalScanner(root=tmp_path / "does-not-exist")
    assert scanner.scan() == []


def test_incremental_scanner_removes_deleted_files(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    assert len(scanner.scan()) == 1

    dst.unlink()
    assert scanner.scan() == []
```

- [ ] **Step 2: Run — expect failures for the new tests**

```bash
python -m pytest tests/test_parser.py -v
```
Expected: the 3 earlier tests pass; new ones fail with `ImportError: cannot import name 'IncrementalScanner'`.

- [ ] **Step 3: Implement IncrementalScanner**

Append to `claude_token_tracker/core/parser.py`:
```python
from dataclasses import dataclass


@dataclass(slots=True)
class _FileState:
    offset: int
    mtime: float
    session: Session


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
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    _ingest_lines(session, f)
                    new_offset = f.tell()
            except OSError:
                return
            self._state[filepath] = _FileState(
                offset=new_offset, mtime=stat.st_mtime, session=session
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
            state.offset = 0

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                f.seek(state.offset)
                _ingest_lines(state.session, f)
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
```

- [ ] **Step 4: Run — expect all parser tests pass**

```bash
python -m pytest tests/test_parser.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/parser.py tests/test_parser.py
git commit -m "core: add IncrementalScanner with offset-tracked re-reads"
```

---

## Task 6: Aggregator — basic rollups

**Files:**
- Create: `claude_token_tracker/core/aggregator.py`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_aggregator.py`:
```python
from datetime import datetime, timezone

from claude_token_tracker.core.aggregator import (
    aggregate_by_model,
    aggregate_by_project,
    aggregate_daily,
    filter_by_range,
)
from claude_token_tracker.core.models import Message, Session, TokenUsage


def _make_session(project: str, model: str, messages: list[tuple[datetime, int]]) -> Session:
    msgs = [
        Message(timestamp=ts, usage=TokenUsage(input=n, output=n, cache_create=n, cache_read=n))
        for ts, n in messages
    ]
    return Session(
        file=f"/tmp/{project}.jsonl",
        project=project,
        session_id=project,
        title=None,
        model=model,
        is_subagent=False,
        messages=msgs,
        first_timestamp=msgs[0].timestamp if msgs else None,
        last_timestamp=msgs[-1].timestamp if msgs else None,
    )


def test_aggregate_daily_buckets_by_date():
    t1 = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc)
    s = _make_session("demo", "claude-opus-4-7", [(t1, 10), (t2, 20), (t3, 5)])
    daily = aggregate_daily([s])
    assert daily["2026-04-15"].input == 30
    assert daily["2026-04-16"].input == 5


def test_aggregate_by_project_sorted_desc():
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s1 = _make_session("small", "claude-opus-4-7", [(t, 5)])
    s2 = _make_session("big", "claude-opus-4-7", [(t, 100)])
    projects = aggregate_by_project([s1, s2])
    assert list(projects.keys()) == ["big", "small"]


def test_aggregate_by_model_sorted_desc():
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s1 = _make_session("p1", "claude-opus-4-7", [(t, 100)])
    s2 = _make_session("p2", "claude-sonnet-4-6", [(t, 50)])
    models = aggregate_by_model([s1, s2])
    assert list(models.keys()) == ["opus-4-7", "sonnet-4-6"]


def test_filter_by_range_24h():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    within = datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)
    out = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session("demo", "claude-opus-4-7", [(within, 10), (out, 20)])
    filtered = filter_by_range([s], range_="24h", now=now)
    assert len(filtered[0].messages) == 1
    assert filtered[0].messages[0].timestamp == within


def test_filter_by_range_all_returns_everything():
    t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 17, tzinfo=timezone.utc)
    s = _make_session("demo", "claude-opus-4-7", [(t1, 5), (t2, 10)])
    filtered = filter_by_range([s], range_="all", now=t2)
    assert len(filtered[0].messages) == 2
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_aggregator.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement basic aggregators**

`claude_token_tracker/core/aggregator.py`:
```python
"""Rollups and derived metrics over lists of Session objects."""
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from .models import Message, Session, TokenUsage
from .pricing import normalize_model

Range = Literal["24h", "7d", "30d", "all"]
VALID_RANGES: frozenset[str] = frozenset({"24h", "7d", "30d", "all"})


def _sum_usage(messages: Iterable[Message]) -> TokenUsage:
    inp = out = cw = cr = 0
    for m in messages:
        inp += m.usage.input
        out += m.usage.output
        cw += m.usage.cache_create
        cr += m.usage.cache_read
    return TokenUsage(input=inp, output=out, cache_create=cw, cache_read=cr)


def aggregate_daily(sessions: Iterable[Session]) -> dict[str, TokenUsage]:
    """Return {YYYY-MM-DD: TokenUsage} sorted by date ascending."""
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        for m in s.messages:
            buckets[m.timestamp.strftime("%Y-%m-%d")].append(m)
    return {day: _sum_usage(msgs) for day, msgs in sorted(buckets.items())}


def aggregate_by_project(sessions: Iterable[Session]) -> dict[str, TokenUsage]:
    """Return {project: TokenUsage} sorted by total descending. Excludes subagents."""
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        if s.is_subagent:
            continue
        buckets[s.project].extend(s.messages)
    totals = {p: _sum_usage(msgs) for p, msgs in buckets.items()}
    return dict(sorted(totals.items(), key=lambda kv: -kv[1].total))


def aggregate_by_model(sessions: Iterable[Session]) -> dict[str, TokenUsage]:
    """Return {normalized_model: TokenUsage} sorted by total descending."""
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        key = normalize_model(s.model)
        buckets[key].extend(s.messages)
    totals = {m: _sum_usage(msgs) for m, msgs in buckets.items()}
    return dict(sorted(totals.items(), key=lambda kv: -kv[1].total))


def filter_by_range(sessions: Iterable[Session], range_: Range, now: datetime) -> list[Session]:
    """Return a new list of sessions with messages filtered to the time window.

    Sessions with zero messages after filtering are dropped.
    """
    if range_ not in VALID_RANGES:
        raise ValueError(f"invalid range: {range_!r}")
    if range_ == "all":
        return list(sessions)

    deltas = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    cutoff = now - deltas[range_]

    out: list[Session] = []
    for s in sessions:
        kept = [m for m in s.messages if m.timestamp >= cutoff]
        if not kept:
            continue
        out.append(replace(
            s,
            messages=kept,
            first_timestamp=kept[0].timestamp,
            last_timestamp=kept[-1].timestamp,
        ))
    return out
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_aggregator.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/aggregator.py tests/test_aggregator.py
git commit -m "core: add daily/project/model rollups and range filter"
```

---

## Task 7: Aggregator — derived metrics

**Files:**
- Modify: `claude_token_tracker/core/aggregator.py`
- Modify: `tests/test_aggregator.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_aggregator.py`:
```python
from claude_token_tracker.core.aggregator import (
    cache_hit_rate,
    peak_hour,
    streak_days,
    total_cache_savings_usd,
)


def test_cache_hit_rate_zero_when_no_input():
    assert cache_hit_rate([]) == 0.0


def test_cache_hit_rate_basic():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-opus-4-7", is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=100, cache_read=900)),
        ],
    )
    # cache_read / (input + cache_read) = 900 / 1000 = 0.9
    assert cache_hit_rate([s]) == 0.9


def test_streak_days_single_today():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(input=1))],
    )
    assert streak_days([s], now=now) == 1


def test_streak_days_consecutive():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    days = [now - timedelta(days=d) for d in range(5)]  # today + 4 prior
    msgs = [Message(timestamp=d, usage=TokenUsage(input=1)) for d in days]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert streak_days([s], now=now) == 5


def test_streak_days_broken_by_gap():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    # Today and 3 days ago (gap of 2)
    msgs = [
        Message(timestamp=now, usage=TokenUsage(input=1)),
        Message(timestamp=now - timedelta(days=3), usage=TokenUsage(input=1)),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert streak_days([s], now=now) == 1


def test_peak_hour_returns_busiest_hour():
    day = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=day, usage=TokenUsage(input=100)),
        Message(timestamp=day.replace(hour=9), usage=TokenUsage(input=10)),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert peak_hour([s]) == 14


def test_peak_hour_none_when_empty():
    assert peak_hour([]) is None


def test_cache_savings_sums_per_model():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s1 = Session(
        file="/tmp/a", project="p", session_id="a", title=None,
        model="claude-opus-4-7", is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(cache_read=1_000_000))],
    )
    s2 = Session(
        file="/tmp/b", project="p", session_id="b", title=None,
        model="claude-sonnet-4-6", is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(cache_read=1_000_000))],
    )
    # Opus: (15 - 1.5) = 13.5 ; Sonnet: (3 - 0.3) = 2.7 → total 16.20
    assert abs(total_cache_savings_usd([s1, s2]) - 16.20) < 0.01


def test_cache_savings_excludes_unknown_model():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="future-model-9000", is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(cache_read=1_000_000))],
    )
    assert total_cache_savings_usd([s]) == 0.0
```

- [ ] **Step 2: Run — expect failures**

```bash
python -m pytest tests/test_aggregator.py -v
```
Expected: the 5 earlier aggregator tests still pass; 8 new ones fail with `ImportError`.

- [ ] **Step 3: Implement derived metrics**

Append to `claude_token_tracker/core/aggregator.py`:
```python
from .pricing import cache_savings_usd


def cache_hit_rate(sessions: Iterable[Session]) -> float:
    """cache_read / (input + cache_read) across all sessions."""
    input_total = 0
    cache_read_total = 0
    for s in sessions:
        for m in s.messages:
            input_total += m.usage.input
            cache_read_total += m.usage.cache_read
    denom = input_total + cache_read_total
    if denom == 0:
        return 0.0
    return cache_read_total / denom


def streak_days(sessions: Iterable[Session], now: datetime) -> int:
    """Consecutive days (ending on ``now``'s date) with at least one message."""
    active: set[str] = set()
    for s in sessions:
        for m in s.messages:
            active.add(m.timestamp.strftime("%Y-%m-%d"))
    count = 0
    day = now.date()
    while day.strftime("%Y-%m-%d") in active:
        count += 1
        day = day - timedelta(days=1)
    return count


def peak_hour(sessions: Iterable[Session]) -> int | None:
    """Hour-of-day (0-23) with the most total tokens. None if no data."""
    buckets: dict[int, int] = defaultdict(int)
    any_data = False
    for s in sessions:
        for m in s.messages:
            buckets[m.timestamp.hour] += m.usage.total
            any_data = True
    if not any_data:
        return None
    return max(buckets.items(), key=lambda kv: kv[1])[0]


def total_cache_savings_usd(sessions: Iterable[Session]) -> float:
    """Sum cache savings across sessions, skipping unknown models."""
    total = 0.0
    for s in sessions:
        cr = sum(m.usage.cache_read for m in s.messages)
        total += cache_savings_usd(s.model, cr)
    return total
```

- [ ] **Step 4: Run — expect all pass**

```bash
python -m pytest tests/test_aggregator.py -v
```
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/aggregator.py tests/test_aggregator.py
git commit -m "core: add cache hit rate, streak, peak hour, cache savings"
```

---

## Task 8: Aggregator — snapshot builder

**Files:**
- Modify: `claude_token_tracker/core/aggregator.py`
- Modify: `tests/test_aggregator.py`

This task produces the single dict returned to JS. One function that combines everything, so the bridge layer is a one-liner.

- [ ] **Step 1: Append failing test**

Append to `tests/test_aggregator.py`:
```python
from claude_token_tracker.core.aggregator import build_snapshot


def test_build_snapshot_shape():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="demo", session_id="x", title="Test", model="claude-opus-4-7",
        is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=100, output=50, cache_read=900)),
        ],
    )
    snap = build_snapshot([s], range_="30d", now=now)
    # Top-level keys
    for key in [
        "range", "generated_at",
        "total_tokens", "today_tokens", "cache_hit_rate", "cache_savings_usd",
        "streak_days", "peak_hour", "active_now_tpm",
        "daily", "heatmap", "by_project", "by_model", "token_mix",
        "sessions",
        "weekly_trend_pct",
    ]:
        assert key in snap, f"missing key: {key}"
    assert snap["range"] == "30d"
    assert snap["total_tokens"] == 100 + 50 + 900
    assert len(snap["sessions"]) == 1
    assert snap["sessions"][0]["title"] == "Test"


def test_build_snapshot_heatmap_shape():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model="claude-opus-4-7",
        is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(input=10))],
    )
    snap = build_snapshot([s], range_="30d", now=now)
    # Heatmap: 7 days × 24 hours = 168 cells of [day_index, hour, value]
    assert len(snap["heatmap"]) == 168
    # Each cell is a 3-element list
    for cell in snap["heatmap"]:
        assert len(cell) == 3
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_aggregator.py -v
```

- [ ] **Step 3: Implement `build_snapshot`**

Append to `claude_token_tracker/core/aggregator.py`:
```python
def _usage_to_dict(u: TokenUsage) -> dict:
    return {
        "input": u.input,
        "output": u.output,
        "cache_create": u.cache_create,
        "cache_read": u.cache_read,
        "total": u.total,
    }


def _active_now_tpm(sessions: Iterable[Session], now: datetime) -> float | None:
    cutoff = now - timedelta(minutes=5)
    recent_total = 0
    recent_any = False
    earliest: datetime | None = None
    for s in sessions:
        for m in s.messages:
            if m.timestamp >= cutoff:
                recent_total += m.usage.total
                recent_any = True
                if earliest is None or m.timestamp < earliest:
                    earliest = m.timestamp
    if not recent_any:
        return None
    span_minutes = max((now - earliest).total_seconds() / 60.0, 0.5)
    return recent_total / span_minutes


def _weekly_trend_pct(sessions: Iterable[Session], now: datetime) -> float:
    this_week = filter_by_range(sessions, "7d", now)
    prev_end = now - timedelta(days=7)
    prev = filter_by_range(sessions, "7d", prev_end)
    this_total = sum(s.total_tokens for s in this_week)
    prev_total = sum(s.total_tokens for s in prev)
    if prev_total == 0:
        return 0.0
    return (this_total - prev_total) / prev_total


def _heatmap(sessions: Iterable[Session]) -> list[list[int]]:
    grid: dict[tuple[int, int], int] = defaultdict(int)
    for s in sessions:
        for m in s.messages:
            # weekday: Mon=0..Sun=6
            grid[(m.timestamp.weekday(), m.timestamp.hour)] += m.usage.total
    cells: list[list[int]] = []
    for d in range(7):
        for h in range(24):
            cells.append([d, h, grid.get((d, h), 0)])
    return cells


def _today_tokens(sessions: Iterable[Session], now: datetime) -> int:
    today_str = now.strftime("%Y-%m-%d")
    total = 0
    for s in sessions:
        for m in s.messages:
            if m.timestamp.strftime("%Y-%m-%d") == today_str:
                total += m.usage.total
    return total


def _session_to_dict(s: Session) -> dict:
    # Velocity sparkline: 8 bars, each = tokens summed in that 1/8 of session lifespan.
    velocity = [0] * 8
    if s.messages and s.first_timestamp and s.last_timestamp:
        start = s.first_timestamp
        span = (s.last_timestamp - start).total_seconds() or 1.0
        for m in s.messages:
            pos = int(((m.timestamp - start).total_seconds() / span) * 8)
            pos = min(max(pos, 0), 7)
            velocity[pos] += m.usage.total
    return {
        "session_id": s.session_id,
        "title": s.title or s.session_id,
        "project": s.project,
        "model": normalize_model(s.model),
        "input_tokens": s.input_tokens,
        "output_tokens": s.output_tokens,
        "cache_create_tokens": s.cache_create_tokens,
        "cache_read_tokens": s.cache_read_tokens,
        "total_tokens": s.total_tokens,
        "velocity": velocity,
        "last_timestamp": s.last_timestamp.isoformat() if s.last_timestamp else None,
        "is_subagent": s.is_subagent,
    }


def build_snapshot(
    sessions: Iterable[Session],
    range_: Range,
    now: datetime,
    project: str | None = None,
) -> dict:
    """Single dict returned to JS with everything the dashboard needs."""
    all_sessions = list(sessions)
    if project:
        all_sessions = [s for s in all_sessions if s.project == project]

    in_range = filter_by_range(all_sessions, range_, now)

    total = sum(s.total_tokens for s in in_range)
    input_sum = sum(s.input_tokens for s in in_range)
    output_sum = sum(s.output_tokens for s in in_range)
    cache_w_sum = sum(s.cache_create_tokens for s in in_range)
    cache_r_sum = sum(s.cache_read_tokens for s in in_range)

    daily = {d: _usage_to_dict(u) for d, u in aggregate_daily(in_range).items()}
    projects = {p: _usage_to_dict(u) for p, u in aggregate_by_project(in_range).items()}
    models = {m: _usage_to_dict(u) for m, u in aggregate_by_model(in_range).items()}

    non_sub = sorted(
        [s for s in in_range if not s.is_subagent],
        key=lambda s: s.last_timestamp or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    hour = peak_hour(in_range)

    return {
        "range": range_,
        "project": project,
        "generated_at": now.isoformat(),
        "total_tokens": total,
        "today_tokens": _today_tokens(all_sessions, now),
        "cache_hit_rate": cache_hit_rate(in_range),
        "cache_savings_usd": total_cache_savings_usd(in_range),
        "streak_days": streak_days(all_sessions, now),
        "peak_hour": hour,
        "active_now_tpm": _active_now_tpm(all_sessions, now),
        "weekly_trend_pct": _weekly_trend_pct(all_sessions, now),
        "daily": daily,
        "heatmap": _heatmap(in_range),
        "by_project": projects,
        "by_model": models,
        "token_mix": {
            "input": input_sum,
            "output": output_sum,
            "cache_create": cache_w_sum,
            "cache_read": cache_r_sum,
        },
        "sessions": [_session_to_dict(s) for s in non_sub[:15]],
    }
```

- [ ] **Step 4: Run — expect all pass**

```bash
python -m pytest tests/test_aggregator.py -v
```
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/core/aggregator.py tests/test_aggregator.py
git commit -m "core: add build_snapshot dashboard payload"
```

---

## Task 9: Bridge API

**Files:**
- Create: `claude_token_tracker/bridge/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from claude_token_tracker.bridge.api import Api


def test_get_dashboard_rejects_invalid_range(tmp_path):
    api = Api(claude_dir=tmp_path, now_fn=lambda: datetime.now(timezone.utc))
    result = api.get_dashboard(range="bogus")
    assert result == {"error": "invalid range"}


def test_get_dashboard_accepts_valid_ranges(tmp_path):
    api = Api(claude_dir=tmp_path, now_fn=lambda: datetime.now(timezone.utc))
    for r in ["24h", "7d", "30d", "all"]:
        result = api.get_dashboard(range=r)
        assert "error" not in result
        assert result["range"] == r


def test_get_dashboard_default_range_is_30d(tmp_path):
    api = Api(claude_dir=tmp_path, now_fn=lambda: datetime.now(timezone.utc))
    result = api.get_dashboard()
    assert result["range"] == "30d"


def test_get_app_info_has_version(tmp_path):
    api = Api(claude_dir=tmp_path, now_fn=lambda: datetime.now(timezone.utc))
    info = api.get_app_info()
    assert "version" in info
    assert "data_source" in info
    assert info["data_source"] == str(tmp_path)
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_api.py -v
```

- [ ] **Step 3: Implement the bridge**

`claude_token_tracker/bridge/api.py`:
```python
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
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_api.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_tracker/bridge/api.py tests/test_api.py
git commit -m "bridge: add narrow-surface Api class"
```

---

## Task 10: UI — vendor libs

**Files:**
- Create: `claude_token_tracker/ui/vendor/alpine.min.js`
- Create: `claude_token_tracker/ui/vendor/echarts.min.js`

- [ ] **Step 1: Download Alpine.js 3.x and ECharts 5.x**

Run from project root:
```bash
mkdir -p claude_token_tracker/ui/vendor
curl -L -o claude_token_tracker/ui/vendor/alpine.min.js \
  https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js
curl -L -o claude_token_tracker/ui/vendor/echarts.min.js \
  https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js
```

- [ ] **Step 2: Verify file sizes (sanity check)**

```bash
ls -l claude_token_tracker/ui/vendor/
```
Expected: `alpine.min.js` ~15 KB, `echarts.min.js` ~1 MB.

- [ ] **Step 3: Commit**

```bash
git add claude_token_tracker/ui/vendor/
git commit -m "ui: vendor Alpine.js 3.14.1 and ECharts 5.5.1"
```

---

## Task 11: UI — HTML shell + CSS

**Files:**
- Create: `claude_token_tracker/ui/index.html`
- Create: `claude_token_tracker/ui/styles.css`

The HTML structure and CSS come directly from the committed mockup. Open it side-by-side while doing this task:
`.superpowers/brainstorm/1965-1776461738/content/dashboard-v1.html`

- [ ] **Step 1: Create `styles.css` by extracting the `<style>` block from the mockup**

Copy the entire contents of the `<style>` tag in `.superpowers/brainstorm/1965-1776461738/content/dashboard-v1.html` (lines 8-330 or thereabouts — everything between `<style>` and `</style>`) into `claude_token_tracker/ui/styles.css` **verbatim**. Do not reformat, do not "improve" — the mockup is ground truth.

- [ ] **Step 2: Create `index.html` shell**

`claude_token_tracker/ui/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy"
  content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'none'; img-src 'self' data:;">
<title>Claude Token Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<script defer src="vendor/alpine.min.js"></script>
<script src="vendor/echarts.min.js"></script>
</head>
<body>
<div class="stage" x-data="dashboard()" x-init="init()">
  <div class="glow g1"></div>
  <div class="glow g2"></div>
  <div class="glow g3"></div>

  <div class="content">
    <!-- Header -->
    <div class="header">
      <div class="logo">
        <div class="logo-dot"></div>
        <div>
          <div class="logo-text">Claude Token Tracker</div>
          <div class="logo-sub">Max plan</div>
        </div>
      </div>
      <div class="header-right">
        <!-- Range filter -->
        <div class="range-filter">
          <template x-for="r in ['24h','7d','30d','all']" :key="r">
            <button
              class="range-btn"
              :class="{'active': range === r}"
              @click="setRange(r)"
              x-text="r"></button>
          </template>
        </div>
        <div class="updated" x-text="'Updated ' + updatedAt"></div>
        <div class="live"><span class="live-dot"></span>LIVE</div>
      </div>
    </div>

    <!-- Hero cards -->
    <div class="hero">
      <div class="glass">
        <div class="card-label"><span class="card-icon">Σ</span>Total tokens</div>
        <div class="hero-value grad-purple" x-text="fmt(data.total_tokens)">—</div>
        <div class="hero-delta" x-text="fmtTrend(data.weekly_trend_pct)">—</div>
        <div class="sparkline" x-html="sparkBars(sparkSeries('total'), 'purple')"></div>
      </div>
      <div class="glass">
        <div class="card-label"><span class="card-icon">◎</span>Today</div>
        <div class="hero-value grad-pink" x-text="fmt(data.today_tokens)">—</div>
        <div class="hero-delta" x-text="(data.sessions?.length ?? 0) + ' recent sessions'"></div>
        <div class="sparkline pink" x-html="sparkBars(sparkSeries('today'), 'pink')"></div>
      </div>
      <div class="glass">
        <div class="card-label"><span class="card-icon">↻</span>Cache hit rate</div>
        <div class="hero-value grad-cyan" x-text="fmtPct(data.cache_hit_rate)">—</div>
        <div class="hero-delta">of input comes from cache</div>
        <div class="sparkline cyan" x-html="sparkBars(sparkSeries('hit'), 'cyan')"></div>
      </div>
      <div class="glass">
        <div class="card-label"><span class="card-icon">$</span>Cache savings</div>
        <div class="hero-value grad-mint" x-text="fmtUsd(data.cache_savings_usd)">—</div>
        <div class="hero-delta">saved vs. no-cache pricing</div>
        <div class="sparkline mint" x-html="sparkBars(sparkSeries('savings'), 'mint')"></div>
      </div>
    </div>

    <!-- Insights strip -->
    <div class="insights">
      <div class="glass chip">
        <div class="chip-icon flame">🔥</div>
        <div>
          <div class="chip-label">Streak</div>
          <div class="chip-value" x-text="(data.streak_days ?? 0) + ' day' + ((data.streak_days === 1) ? '' : 's') + ' in a row'"></div>
        </div>
      </div>
      <div class="glass chip">
        <div class="chip-icon clock">⏰</div>
        <div>
          <div class="chip-label">Peak hour</div>
          <div class="chip-value" x-text="fmtHour(data.peak_hour)"></div>
        </div>
      </div>
      <div class="glass chip">
        <div class="chip-icon bolt">⚡</div>
        <div>
          <div class="chip-label">Active now</div>
          <div class="chip-value" x-text="fmtActive(data.active_now_tpm)"></div>
        </div>
      </div>
    </div>

    <!-- Main charts -->
    <div class="main-charts">
      <div class="glass">
        <div class="chart-title">30-day token usage</div>
        <div class="chart-sub">Stacked by type · 7-day moving average overlay</div>
        <div id="chart-daily" class="area-wrap"></div>
      </div>
      <div class="glass">
        <div class="chart-title">Activity heatmap</div>
        <div class="chart-sub">When do you use Claude? · Day of week × hour</div>
        <div id="chart-heatmap" style="height: 240px; margin-top: 8px;"></div>
      </div>
    </div>

    <!-- Breakdowns -->
    <div class="breakdown">
      <div class="glass">
        <div class="chart-title">Token mix</div>
        <div class="chart-sub" x-text="'Range: ' + range"></div>
        <div id="chart-donut" style="height: 260px;"></div>
      </div>
      <div class="glass">
        <div class="chart-title">Tokens by project</div>
        <div class="chart-sub">Top 6 · click to filter</div>
        <div id="chart-projects" style="height: 260px; margin-top: 8px;"></div>
      </div>
      <div class="glass">
        <div class="chart-title">Tokens by model</div>
        <div class="chart-sub" x-text="'Range: ' + range"></div>
        <div id="chart-models" style="height: 260px; margin-top: 8px;"></div>
      </div>
    </div>

    <!-- Sessions table -->
    <div class="glass session-table">
      <div class="session-head">
        <div class="chart-title">Recent sessions</div>
        <div class="chart-sub" style="margin:0" x-text="(data.sessions?.length ?? 0) + ' shown'"></div>
      </div>
      <div class="session-rows">
        <div class="session-row header">
          <div>Session</div><div>Project</div><div>Model</div>
          <div>In</div><div>Out</div><div>Velocity</div><div>When</div>
        </div>
        <template x-for="s in (data.sessions ?? [])" :key="s.session_id">
          <div class="session-row">
            <div class="session-title" x-text="s.title"></div>
            <div class="session-project" x-text="s.project"></div>
            <div class="session-model" x-text="s.model"></div>
            <div class="session-num in" x-text="fmt(s.input_tokens)"></div>
            <div class="session-num out" x-text="fmt(s.output_tokens)"></div>
            <div class="mini-spark" x-html="sparkBars(s.velocity, 'purple')"></div>
            <div class="session-when" x-text="fmtWhen(s.last_timestamp)"></div>
          </div>
        </template>
      </div>
    </div>

  </div>
</div>

<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Add range-filter styles to `styles.css`**

Append to `claude_token_tracker/ui/styles.css`:
```css
/* Range filter segmented control */
.range-filter {
  display: flex;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 999px;
  padding: 3px;
  backdrop-filter: blur(12px);
}
.range-btn {
  background: transparent;
  border: none;
  color: var(--dim, rgba(255,255,255,0.6));
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.range-btn:hover { color: #fff; }
.range-btn.active {
  background: rgba(255,255,255,0.12);
  color: #fff;
  box-shadow: 0 0 12px rgba(139,92,246,0.3);
}
```

- [ ] **Step 4: Commit**

```bash
git add claude_token_tracker/ui/index.html claude_token_tracker/ui/styles.css
git commit -m "ui: HTML shell with CSP + extracted mockup CSS"
```

---

## Task 12: UI — app.js (state + formatters + bridge call)

**Files:**
- Create: `claude_token_tracker/ui/app.js`

- [ ] **Step 1: Write the Alpine dashboard component**

`claude_token_tracker/ui/app.js`:
```javascript
/* global Alpine, echarts, pywebview */

function dashboard() {
  return {
    range: "30d",
    data: {},
    updatedAt: "—",
    charts: { daily: null, heatmap: null, donut: null, projects: null, models: null },

    async init() {
      this._initCharts();
      await this.refresh();
      // Auto-refresh every 5s. Bridge returns fast when nothing changed.
      setInterval(() => this.refresh(), 5000);
      window.addEventListener("resize", () => this._resizeCharts());
    },

    async refresh() {
      if (!window.pywebview?.api?.get_dashboard) return;
      const snap = await window.pywebview.api.get_dashboard(this.range, null);
      if (snap && !snap.error) {
        this.data = snap;
        this.updatedAt = new Date().toLocaleTimeString([], { hour12: false });
        this._renderCharts();
      }
    },

    setRange(r) {
      this.range = r;
      this.refresh();
    },

    // ── Formatters ──
    fmt(n) {
      if (n == null) return "—";
      if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
      if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
      return String(n);
    },
    fmtPct(x) {
      if (x == null) return "—";
      return (x * 100).toFixed(1) + "%";
    },
    fmtUsd(x) {
      if (x == null) return "—";
      return "$" + x.toFixed(2);
    },
    fmtTrend(pct) {
      if (pct == null || pct === 0) return "—";
      const arrow = pct >= 0 ? "↑" : "↓";
      return arrow + " " + (pct * 100).toFixed(1) + "% vs last week";
    },
    fmtHour(h) {
      if (h == null) return "—";
      const hr12 = ((h + 11) % 12) + 1;
      const ampm = h < 12 ? "AM" : "PM";
      const next12 = ((h + 1 + 11) % 12) + 1;
      const nextAmPm = (h + 1) % 24 < 12 ? "AM" : "PM";
      return `${hr12} – ${next12} ${nextAmPm}`;
    },
    fmtActive(tpm) {
      if (tpm == null) return "Idle";
      return this.fmt(Math.round(tpm)) + " tok / min";
    },
    fmtWhen(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now - d;
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return mins + "m ago";
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return hrs + "h ago";
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    },

    sparkSeries(which) {
      // Last 12 days of totals/slice-specific values for the hero-card sparkline.
      const daily = this.data.daily || {};
      const days = Object.keys(daily).slice(-12);
      return days.map((d) => {
        const row = daily[d];
        if (which === "total") return row.total;
        if (which === "today") return row.total; // same daily total, pink color
        if (which === "hit") {
          const denom = row.input + row.cache_read;
          return denom > 0 ? row.cache_read / denom : 0;
        }
        if (which === "savings") return row.cache_read; // proxy: cache reads → savings
        return 0;
      });
    },

    sparkBars(values, _cls) {
      if (!values || values.length === 0) {
        return Array(8).fill('<span style="height:5%"></span>').join("");
      }
      const max = Math.max(...values, 1);
      return values
        .map((v) => `<span style="height:${Math.max(5, (v / max) * 100)}%"></span>`)
        .join("");
    },

    // ── Charts ──
    _initCharts() {
      this.charts.daily = echarts.init(document.getElementById("chart-daily"));
      this.charts.heatmap = echarts.init(document.getElementById("chart-heatmap"));
      this.charts.donut = echarts.init(document.getElementById("chart-donut"));
      this.charts.projects = echarts.init(document.getElementById("chart-projects"));
      this.charts.models = echarts.init(document.getElementById("chart-models"));
    },

    _resizeCharts() {
      Object.values(this.charts).forEach((c) => c && c.resize());
    },

    _renderCharts() {
      this._renderDaily();
      this._renderHeatmap();
      this._renderDonut();
      this._renderProjects();
      this._renderModels();
    },

    _renderDaily() {
      const daily = this.data.daily || {};
      const dates = Object.keys(daily);
      const axis = dates.map((d) => d.slice(5));
      const input = dates.map((d) => daily[d].input);
      const output = dates.map((d) => daily[d].output);
      const cacheW = dates.map((d) => daily[d].cache_create);
      const cacheR = dates.map((d) => daily[d].cache_read);
      // 7-day moving avg of totals
      const totals = dates.map((d) => daily[d].total);
      const avg = totals.map((_, i) => {
        const win = totals.slice(Math.max(0, i - 6), i + 1);
        return win.reduce((a, b) => a + b, 0) / win.length;
      });

      const mkSeries = (name, data, color) => ({
        name,
        type: "line",
        stack: "tokens",
        smooth: true,
        showSymbol: false,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: color + "e6" },
            { offset: 1, color: color + "0d" },
          ]),
        },
        lineStyle: { width: 0 },
        data,
      });

      this.charts.daily.setOption(
        {
          animationDuration: 600,
          grid: { left: 40, right: 16, top: 20, bottom: 30 },
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
          legend: { show: false },
          xAxis: { type: "category", data: axis, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10 } },
          yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(255,255,255,0.07)" } }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          series: [
            mkSeries("Input",       input,  "#60a5fa"),
            mkSeries("Output",      output, "#ec4899"),
            mkSeries("Cache write", cacheW, "#fbbf24"),
            mkSeries("Cache read",  cacheR, "#34d399"),
            {
              name: "7-day avg",
              type: "line",
              smooth: true,
              showSymbol: false,
              lineStyle: { color: "#ffffff", width: 2, type: "dashed" },
              data: avg,
            },
          ],
        },
        { notMerge: false },
      );
    },

    _renderHeatmap() {
      const cells = this.data.heatmap || [];
      const maxVal = cells.reduce((m, c) => Math.max(m, c[2]), 0) || 1;
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      this.charts.heatmap.setOption(
        {
          tooltip: {
            formatter: (p) => `${days[p.data[0]]} ${p.data[1]}:00 — ${this.fmt(p.data[2])}`,
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
          },
          grid: { left: 40, right: 16, top: 16, bottom: 30 },
          xAxis: { type: "category", data: Array.from({ length: 24 }, (_, i) => i), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 9, interval: 2 } },
          yAxis: { type: "category", data: days, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10 } },
          visualMap: {
            min: 0, max: maxVal, show: false,
            inRange: { color: ["rgba(139,92,246,0.08)", "#8b5cf6", "#ec4899"] },
          },
          series: [{ type: "heatmap", data: cells, itemStyle: { borderRadius: 3 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(236,72,153,0.6)" } } }],
        },
        { notMerge: false },
      );
    },

    _renderDonut() {
      const m = this.data.token_mix || { input: 0, output: 0, cache_create: 0, cache_read: 0 };
      this.charts.donut.setOption(
        {
          tooltip: { trigger: "item", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
          legend: { bottom: 0, textStyle: { color: "rgba(255,255,255,0.75)", fontSize: 11 }, itemWidth: 10, itemHeight: 10, icon: "roundRect" },
          series: [{
            type: "pie",
            radius: ["55%", "80%"],
            center: ["50%", "45%"],
            label: { show: false },
            labelLine: { show: false },
            data: [
              { value: m.input, name: "Input", itemStyle: { color: "#60a5fa" } },
              { value: m.output, name: "Output", itemStyle: { color: "#ec4899" } },
              { value: m.cache_create, name: "Cache W", itemStyle: { color: "#fbbf24" } },
              { value: m.cache_read, name: "Cache R", itemStyle: { color: "#34d399" } },
            ],
          }],
        },
        { notMerge: false },
      );
    },

    _renderProjects() {
      const by = this.data.by_project || {};
      const names = Object.keys(by).slice(0, 6).reverse(); // reversed for top-down in horizontal bar
      const input = names.map((n) => by[n].input);
      const output = names.map((n) => by[n].output);
      const cw = names.map((n) => by[n].cache_create);
      const cr = names.map((n) => by[n].cache_read);
      const mkBar = (name, data, color) => ({
        name, type: "bar", stack: "t", data,
        itemStyle: { color, borderRadius: [0, 0, 0, 0] },
      });
      this.charts.projects.setOption(
        {
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
          grid: { left: 110, right: 30, top: 8, bottom: 20 },
          xAxis: { type: "value", splitLine: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          yAxis: { type: "category", data: names, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11 } },
          series: [
            mkBar("Input", input, "#60a5fa"),
            mkBar("Output", output, "#ec4899"),
            mkBar("Cache W", cw, "#fbbf24"),
            mkBar("Cache R", cr, "#34d399"),
          ],
        },
        { notMerge: false },
      );
    },

    _renderModels() {
      const by = this.data.by_model || {};
      const names = Object.keys(by).slice(0, 6).reverse();
      const totals = names.map((n) => by[n].total);
      const colors = ["#8b5cf6", "#06b6d4", "#34d399", "#ec4899", "#fbbf24", "#f97316"];
      this.charts.models.setOption(
        {
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
          grid: { left: 90, right: 40, top: 8, bottom: 20 },
          xAxis: { type: "value", splitLine: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          yAxis: { type: "category", data: names, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11, fontFamily: "JetBrains Mono" } },
          series: [{
            type: "bar",
            data: totals.map((v, i) => ({ value: v, itemStyle: { color: colors[i % colors.length], borderRadius: 999 } })),
          }],
        },
        { notMerge: false },
      );
    },
  };
}

// Register the Alpine component on load
document.addEventListener("alpine:init", () => {
  Alpine.data("dashboard", dashboard);
});
```

- [ ] **Step 2: Commit**

```bash
git add claude_token_tracker/ui/app.js
git commit -m "ui: Alpine dashboard component + ECharts wiring"
```

---

## Task 13: Entrypoint `app.py`

**Files:**
- Create: `app.py`

- [ ] **Step 1: Write the entrypoint**

`app.py`:
```python
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
        min_size=(1100, 760),
        background_color="#0a0a0f",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run from source**

```bash
python app.py
```
Expected: A dark gradient window opens showing the dashboard. Scroll through — no console errors. Close the window.

If the window is blank: open DevTools via right-click → Inspect (pywebview supports this when `debug=True`; if you need it, re-run with `debug=True` once temporarily).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "app: entrypoint wiring pywebview + bridge"
```

---

## Task 14: PyInstaller spec update

**Files:**
- Modify: `ClaudeTokenTracker.spec`
- Modify: `.gitignore`

- [ ] **Step 1: Remove `*.spec` from `.gitignore`**

Open `.gitignore` and delete the single line `*.spec`. (We want the PyInstaller spec file tracked.) Save.

- [ ] **Step 2: Replace `ClaudeTokenTracker.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('claude_token_tracker/ui', 'claude_token_tracker/ui'),
    ],
    hiddenimports=collect_submodules('webview'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ClaudeTokenTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 3: Build and smoke-test the exe**

```bash
python -m PyInstaller ClaudeTokenTracker.spec --clean --noconfirm
./dist/ClaudeTokenTracker.exe
```
Expected: The same dashboard window opens; close it.

- [ ] **Step 4: Commit**

```bash
git add ClaudeTokenTracker.spec .gitignore
git commit -m "build: update PyInstaller spec to bundle ui/ and track it"
```

---

## Task 15: Remove the old app + final verification

**Files:**
- Delete: `claude_token_tracker.py` (the original 745-line monolith)

- [ ] **Step 1: Confirm the new app works, then delete the old one**

```bash
python app.py
```
Close the window.

```bash
git rm claude_token_tracker.py
```

- [ ] **Step 2: Run the full test suite**

```bash
python -m pytest -v
```
Expected: all tests pass (models + pricing + parser + aggregator + api = ~30 tests).

- [ ] **Step 3: Final check — no residual references**

```bash
grep -r "customtkinter\|matplotlib" . --include="*.py" --include="*.bat" --include="*.spec" --include="*.txt" --exclude-dir=.git --exclude-dir=build --exclude-dir=dist --exclude-dir=__pycache__ || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 4: Commit**

```bash
git commit -m "remove legacy monolith claude_token_tracker.py"
```

- [ ] **Step 5: Tag the release**

```bash
git tag -a v2.0.0 -m "v2.0.0 — glassmorphism redesign"
```

---

## Definition of Done

All of these are true:

- [ ] `python -m pytest -v` → all tests pass.
- [ ] `python app.py` → window opens, dashboard renders, no console errors, live dot pulses, data matches current `~/.claude/projects` usage.
- [ ] All five rows from the spec are present: header, hero cards, insights, main charts, breakdowns, sessions table.
- [ ] Changing time-range buttons re-renders every widget in under 1 second.
- [ ] Cold-start < 200 ms with ~500 sessions cached (measure via `time python -c "from claude_token_tracker.bridge.api import Api; from pathlib import Path; from datetime import datetime, timezone; a = Api(Path.home() / '.claude' / 'projects'); a.get_dashboard()"`).
- [ ] Second refresh with no file changes returns in under 10 ms (measured same way, two consecutive calls).
- [ ] No CDN / network requests at runtime (verified: disable network, app still renders).
- [ ] `./dist/ClaudeTokenTracker.exe` (PyInstaller build) opens and works identically to `python app.py`.
- [ ] No user email/PII visible anywhere in the UI.
- [ ] Old `claude_token_tracker.py` is deleted.
