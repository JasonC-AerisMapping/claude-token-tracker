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
