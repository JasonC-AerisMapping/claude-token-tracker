from datetime import datetime, timezone

from prompt_ledger.core.aggregator import (
    aggregate_by_model,
    aggregate_by_project,
    aggregate_daily,
    filter_by_range,
)
from prompt_ledger.core.models import Message, Session, TokenUsage


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

from datetime import timedelta

from prompt_ledger.core.aggregator import (
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


from prompt_ledger.core.aggregator import build_snapshot


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
    for cell in snap["heatmap"]:
        assert len(cell) == 3
