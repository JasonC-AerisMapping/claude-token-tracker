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
