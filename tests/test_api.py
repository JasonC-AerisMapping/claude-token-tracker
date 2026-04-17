import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from claude_token_tracker.bridge.api import Api


def _write_session(root: Path, project: str, session_id: str, *, ts="2026-04-15T12:00:00Z") -> Path:
    proj_dir = root / project
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / f"{session_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "type": "assistant",
            "timestamp": ts,
            "sessionId": session_id,
            "message": {
                "model": "claude-opus-4-7",
                "usage": {"input_tokens": 100, "output_tokens": 50,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }) + "\n")
    return path


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


def test_export_csv_writes_rows(tmp_path):
    _write_session(tmp_path, "proj--a", "sess-1")
    _write_session(tmp_path, "proj--b", "sess-2")
    out = tmp_path / "out.csv"
    api = Api(
        claude_dir=tmp_path,
        now_fn=lambda: datetime.now(timezone.utc),
        save_dialog_fn=lambda name: str(out),
    )
    assert api.export_csv() is True
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0][0] == "session_id"
    assert {r[0] for r in rows[1:]} == {"sess-1", "sess-2"}


def test_export_csv_cancelled_returns_false(tmp_path):
    api = Api(
        claude_dir=tmp_path,
        now_fn=lambda: datetime.now(timezone.utc),
        save_dialog_fn=lambda name: None,
    )
    assert api.export_csv() is False


def test_open_session_folder_unknown_id_returns_false(tmp_path):
    revealed: list[Path] = []
    api = Api(
        claude_dir=tmp_path,
        now_fn=lambda: datetime.now(timezone.utc),
        reveal_fn=revealed.append,
    )
    assert api.open_session_folder("does-not-exist") is False
    assert revealed == []


def test_open_session_folder_reveals_parent_of_jsonl(tmp_path):
    _write_session(tmp_path, "proj--a", "sess-1")
    revealed: list[Path] = []
    api = Api(
        claude_dir=tmp_path,
        now_fn=lambda: datetime.now(timezone.utc),
        reveal_fn=revealed.append,
    )
    assert api.open_session_folder("sess-1") is True
    assert revealed == [tmp_path / "proj--a"]
