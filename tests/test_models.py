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
