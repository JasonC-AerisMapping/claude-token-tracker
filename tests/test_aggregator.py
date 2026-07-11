from datetime import datetime, timezone

from prompt_ledger.core.aggregator import (
    aggregate_by_model,
    aggregate_by_project,
    aggregate_daily,
    aggregate_series,
    build_snapshot,
    filter_by_range,
    project_label,
    session_cost_usd,
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
    cache_efficiency,
    cache_reuse_ratio,
    peak_hour,
    streak_days,
    total_cache_savings_usd,
)


def test_cache_efficiency_zero_when_no_data():
    assert cache_efficiency([]) == 0.0


def test_cache_efficiency_basic():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-opus-4-7", is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=100, cache_read=900)),
        ],
    )
    # cache_read / (input + cache_read + cache_create) = 900 / (100 + 900 + 0) = 0.9
    assert cache_efficiency([s]) == 0.9


def test_cache_efficiency_penalizes_cache_writes():
    # Same 900 cache reads, but now 500 cache_create → denominator grows.
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-opus-4-7", is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(input=100, cache_create=500, cache_read=900)),
        ],
    )
    # 900 / (100 + 900 + 500) = 0.6
    assert cache_efficiency([s]) == 0.6


def test_cache_reuse_ratio_zero_when_no_writes():
    assert cache_reuse_ratio([]) == 0.0


def test_cache_reuse_ratio_basic():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-opus-4-7", is_subagent=False,
        messages=[
            Message(timestamp=now, usage=TokenUsage(cache_create=100, cache_read=350)),
        ],
    )
    # 350 / 100 = 3.5
    assert cache_reuse_ratio([s]) == 3.5


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
    # 14:30 UTC on 2026-04-15 → 10:30 EDT. Peak hour should be reported in local tz.
    day = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=day, usage=TokenUsage(input=100)),
        Message(timestamp=day.replace(hour=9), usage=TokenUsage(input=10)),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert peak_hour([s]) == 10


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
    # Opus 4.7: (5 - 0.5) = 4.5 ; Sonnet 4.6: (3 - 0.3) = 2.7 → total 7.20
    assert abs(total_cache_savings_usd([s1, s2]) - 7.20) < 0.01


def test_cache_savings_excludes_unknown_model():
    now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="future-model-9000", is_subagent=False,
        messages=[Message(timestamp=now, usage=TokenUsage(cache_read=1_000_000))],
    )
    assert total_cache_savings_usd([s]) == 0.0


def test_aggregate_by_project_includes_subagents():
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    main = _make_session("proj", "claude-opus-4-8", [(t, 10)])
    sub = _make_session("proj", "claude-opus-4-8", [(t, 5)])
    sub.is_subagent = True
    projects = aggregate_by_project([main, sub])
    assert projects["proj"].input == 15


def test_project_label_shortens_long_paths():
    long = "Users/jason/OneDrive/Desktop/Claude/Cowork/for/Aeris/Mapping"
    assert project_label(long) == "…/Aeris/Mapping"
    assert project_label("short/name") == "short/name"


def _session_with_cwd(project: str, cwd: str | None, subagent: bool = False) -> Session:
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session(project, "claude-opus-4-8", [(t, 10)])
    s.cwd = cwd
    s.is_subagent = subagent
    return s


def test_derive_project_labels_uses_cwd_basename():
    from prompt_ledger.core.aggregator import derive_project_labels
    s = _session_with_cwd(
        "Users/jason/OneDrive/Desktop/Claude/Output/claude/token/tracker",
        "C:\\Users\\jason\\OneDrive\\Desktop\\Claude Output\\claude-token-tracker",
    )
    labels = derive_project_labels([s])
    assert labels[s.project] == "claude-token-tracker"


def test_derive_project_labels_prefers_main_session_cwd():
    from prompt_ledger.core.aggregator import derive_project_labels
    main = _session_with_cwd("proj", "C:\\Users\\j\\Merlin")
    sub = _session_with_cwd("proj", "C:\\worktrees\\merlin-wt-1", subagent=True)
    labels = derive_project_labels([main, sub, sub])
    assert labels["proj"] == "Merlin"


def test_derive_project_labels_disambiguates_shared_basenames():
    from prompt_ledger.core.aggregator import derive_project_labels
    a = _session_with_cwd("p/a", "C:\\code\\alpha\\dashboard")
    b = _session_with_cwd("p/b", "C:\\code\\beta\\dashboard")
    labels = derive_project_labels([a, b])
    assert labels["p/a"] == "alpha/dashboard"
    assert labels["p/b"] == "beta/dashboard"
    assert len(set(labels.values())) == 2


def test_derive_project_labels_falls_back_without_cwd():
    from prompt_ledger.core.aggregator import derive_project_labels
    s = _session_with_cwd("Users/x/Deep/Nested/Project", None)
    labels = derive_project_labels([s])
    assert labels[s.project] == "…/Nested/Project"


def test_derive_project_labels_merges_case_variants_of_same_cwd():
    from prompt_ledger.core.aggregator import derive_project_labels, project_real_paths
    s1 = _session_with_cwd("proj", "C:\\Users\\j\\Merlin")
    s2 = _session_with_cwd("proj", "c:\\Users\\j\\Merlin")
    assert project_real_paths([s1, s2])["proj"] == "C:/Users/j/Merlin"
    assert derive_project_labels([s1, s2])["proj"] == "Merlin"


def test_cost_mix_by_type_known_model():
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session("p", "claude-opus-4-8", [(t, 1_000_000)])
    snap = build_snapshot([s], range_="7d", now=now)
    mix = snap["cost_mix"]
    # 1M tokens of each type on opus-4-8: 5.00 / 25.00 / 6.25 / 0.50
    assert abs(mix["input"] - 5.00) < 1e-9
    assert abs(mix["output"] - 25.00) < 1e-9
    assert abs(mix["cache_create"] - 6.25) < 1e-9
    assert abs(mix["cache_read"] - 0.50) < 1e-9
    # Segments must sum to the headline cost estimate.
    assert abs(sum(mix.values()) - snap["est_cost_usd"]) < 1e-6


def test_cost_mix_excludes_unknown_models():
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session("p", "future-model-9000", [(t, 1_000_000)])
    snap = build_snapshot([s], range_="7d", now=now)
    assert snap["cost_mix"] == {
        "input": 0.0, "output": 0.0, "cache_create": 0.0, "cache_read": 0.0,
    }


def test_build_snapshot_project_paths_and_cwd_labels():
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    s = _session_with_cwd("proj", "C:\\Users\\j\\Merlin")
    snap = build_snapshot([s], range_="7d", now=now)
    assert snap["project_paths"]["proj"] == "C:/Users/j/Merlin"
    assert snap["project_labels"]["proj"] == "Merlin"
    assert snap["sessions"][0]["project_label"] == "Merlin"


def test_aggregate_series_24h_is_hourly_and_zero_filled():
    now = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    t = datetime(2026, 4, 15, 13, 5, tzinfo=timezone.utc)  # within last 24h
    s = _make_session("p", "claude-opus-4-8", [(t, 42)])
    series = aggregate_series([s], "24h", now)
    assert len(series) == 24
    assert all(":" in k for k in series)
    assert sum(u.input for u in series.values()) == 42


def test_aggregate_series_7d_zero_fills_gaps():
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
    s = _make_session("p", "claude-opus-4-8", [(t, 7)])
    series = aggregate_series([s], "7d", now)
    assert len(series) == 7
    zero_days = [k for k, u in series.items() if u.total == 0]
    assert len(zero_days) == 6


def test_session_cost_usd_known_model():
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session("p", "claude-opus-4-8", [(t, 1_000_000)])
    # 1M each of input/output/cache_create/cache_read on opus-4-8 = 36.75
    assert abs(session_cost_usd(s) - 36.75) < 0.01


def test_build_snapshot_carries_cost_and_labels():
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    s = _make_session("Users/x/Deep/Nested/Project", "claude-opus-4-8", [(t, 1000)])
    snap = build_snapshot([s], range_="7d", now=now)
    assert snap["est_cost_usd"] > 0
    assert snap["all_projects"] == ["Users/x/Deep/Nested/Project"]
    assert snap["project_labels"]["Users/x/Deep/Nested/Project"] == "…/Nested/Project"
    proj = snap["by_project"]["Users/x/Deep/Nested/Project"]
    assert "est_cost_usd" in proj
    model = snap["by_model"]["opus-4-8"]
    assert "est_cost_usd" in model
    assert snap["sessions"][0]["est_cost_usd"] > 0
    assert snap["sessions"][0]["project_label"] == "…/Nested/Project"


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
        "total_tokens", "today_tokens", "cache_efficiency", "cache_reuse_ratio", "cache_savings_usd",
        "streak_days", "peak_hour", "active_now_tpm",
        "daily", "heatmap", "by_project", "by_model", "token_mix",
        "cost_mix", "project_paths",
        "sessions",
        "trend_pct",
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
    # Heatmap: 7 days × 24 hours = 168 cells of [hour, day_index, value]
    # (ECharts heatmap convention: [xIndex, yIndex, value]; xAxis=hours, yAxis=days)
    assert len(snap["heatmap"]) == 168
    for cell in snap["heatmap"]:
        assert len(cell) == 3
        assert 0 <= cell[0] <= 23, f"hour out of range: {cell}"
        assert 0 <= cell[1] <= 6, f"day out of range: {cell}"


def test_trend_pct_equal_windows_is_zero():
    # 100 tokens this week + 100 tokens previous week → trend should be 0%.
    from prompt_ledger.core.aggregator import _trend_pct
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    this_msg = Message(timestamp=now - timedelta(days=3), usage=TokenUsage(input=100))
    prev_msg = Message(timestamp=now - timedelta(days=10), usage=TokenUsage(input=100))
    s = Session(
        file="/x", project="p", session_id="s", title=None, model="claude-opus-4-7",
        is_subagent=False,
        messages=[prev_msg, this_msg],
    )
    assert _trend_pct([s], "7d", now) == 0.0


def test_trend_pct_this_window_double_prev():
    # 200 this week, 100 previous week → +100%.
    from prompt_ledger.core.aggregator import _trend_pct
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=now - timedelta(days=3), usage=TokenUsage(input=200)),
        Message(timestamp=now - timedelta(days=10), usage=TokenUsage(input=100)),
    ]
    s = Session(
        file="/x", project="p", session_id="s", title=None, model="claude-opus-4-7",
        is_subagent=False, messages=msgs,
    )
    assert _trend_pct([s], "7d", now) == 1.0


def test_trend_pct_window_matches_selected_range():
    # 24h view must compare the last 24h to the 24h before it — not fixed
    # 7-day windows. 300 tokens in the last day, 100 the day before, plus
    # noise earlier in the week that a 7d window would sweep in.
    from prompt_ledger.core.aggregator import _trend_pct
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=now - timedelta(hours=2), usage=TokenUsage(input=300)),
        Message(timestamp=now - timedelta(hours=30), usage=TokenUsage(input=100)),
        Message(timestamp=now - timedelta(days=5), usage=TokenUsage(input=9999)),
    ]
    s = Session(
        file="/x", project="p", session_id="s", title=None, model="claude-opus-4-7",
        is_subagent=False, messages=msgs,
    )
    assert _trend_pct([s], "24h", now) == 2.0  # (300-100)/100
    assert _trend_pct([s], "all", now) is None  # no prior window for "all"


def test_streak_survives_quiet_morning():
    # Active yesterday and the day before, nothing yet today → streak is 2,
    # not 0. It only breaks once today ends without activity.
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=now - timedelta(days=1), usage=TokenUsage(input=1)),
        Message(timestamp=now - timedelta(days=2), usage=TokenUsage(input=1)),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert streak_days([s], now=now) == 2


def test_peak_hour_tie_breaks_to_earliest_hour():
    # Equal token counts at two hours → earliest hour wins, deterministically.
    base = datetime(2026, 4, 15, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=base.replace(hour=18), usage=TokenUsage(input=50)),  # 14 EDT
        Message(timestamp=base.replace(hour=13), usage=TokenUsage(input=50)),  # 9 EDT
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model=None,
        is_subagent=False, messages=msgs,
    )
    assert peak_hour([s]) == 9


def test_series_24h_sums_to_window_total():
    # A message inside the 24h window whose Eastern hour precedes the first
    # chart bucket must be clamped into it, not dropped — the chart always
    # sums to the headline total above it.
    now = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    in_bucket = datetime(2026, 4, 15, 13, 5, tzinfo=timezone.utc)
    edge = now - timedelta(hours=23, minutes=50)  # in window, before bucket 0
    s = _make_session("p", "claude-opus-4-8", [(in_bucket, 42), (edge, 8)])
    in_range = filter_by_range([s], "24h", now)
    series = aggregate_series(in_range, "24h", now)
    window_total = sum(sess.total_tokens for sess in in_range)
    assert sum(u.total for u in series.values()) == window_total
    assert len(series) == 24


def test_series_7d_clamps_window_edge_into_first_day():
    # Same invariant for daily buckets: a message inside the rolling 7d UTC
    # window but on the Eastern calendar day before the first bucket lands
    # in the first bucket instead of vanishing.
    now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    edge = now - timedelta(days=6, hours=20)  # inside window, prior local day
    s = _make_session("p", "claude-opus-4-8", [(edge, 11), (now, 5)])
    in_range = filter_by_range([s], "7d", now)
    series = aggregate_series(in_range, "7d", now)
    window_total = sum(sess.total_tokens for sess in in_range)
    assert sum(u.total for u in series.values()) == window_total
    assert len(series) == 7


def test_session_cost_mixed_models_priced_per_message():
    # A session that starts on haiku and switches to opus must not price the
    # opus tokens at haiku rates.
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=t, usage=TokenUsage(output=1_000_000), model="claude-haiku-4-5"),
        Message(timestamp=t, usage=TokenUsage(output=1_000_000), model="claude-opus-4-8"),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-haiku-4-5", is_subagent=False, messages=msgs,
    )
    # 1M output on haiku ($5) + 1M output on opus ($25) = $30, not $10.
    assert abs(session_cost_usd(s) - 30.0) < 1e-9


def test_aggregate_by_model_splits_within_session():
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=t, usage=TokenUsage(input=100), model="claude-haiku-4-5"),
        Message(timestamp=t, usage=TokenUsage(input=900), model="claude-opus-4-8"),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-haiku-4-5", is_subagent=False, messages=msgs,
    )
    models = aggregate_by_model([s])
    assert models["haiku-4-5"].input == 100
    assert models["opus-4-8"].input == 900


def test_synthetic_first_line_does_not_dump_session_into_unknown():
    # A session whose first assistant line is a <synthetic> error placeholder
    # must not attribute the real messages (which carry their own model) to
    # "unknown" at $0.
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    msgs = [
        Message(timestamp=t, usage=TokenUsage(output=1_000_000), model="claude-opus-4-8"),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="<synthetic>", is_subagent=False, messages=msgs,
    )
    models = aggregate_by_model([s])
    assert "unknown" not in models
    assert models["opus-4-8"].output == 1_000_000
    assert abs(session_cost_usd(s) - 25.0) < 1e-9


def test_cache_write_1h_priced_at_2x_input():
    # 1M cache-create tokens, all 1h-TTL, on opus-4-8: $10, not $6.25.
    t = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    msgs = [
        Message(
            timestamp=t,
            usage=TokenUsage(cache_create=1_000_000, cache_create_1h=1_000_000),
            model="claude-opus-4-8",
        ),
    ]
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None,
        model="claude-opus-4-8", is_subagent=False, messages=msgs,
    )
    assert abs(session_cost_usd(s) - 10.0) < 1e-9


def test_build_snapshot_heatmap_places_cell_at_hour_day():
    # 2026-04-17 12:00 UTC = 2026-04-17 08:00 America/New_York (EDT).
    # Weekday==4 (Fri) in both zones; local hour==8.
    ts = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model="claude-opus-4-7",
        is_subagent=False,
        messages=[Message(timestamp=ts, usage=TokenUsage(input=7, output=3))],
    )
    snap = build_snapshot([s], range_="30d", now=ts)
    nonzero = [c for c in snap["heatmap"] if c[2] != 0]
    assert nonzero == [[8, 4, 10]], f"unexpected cells: {nonzero}"


def test_eastern_date_bucketing_wraps_late_utc_to_prev_local_day():
    # Message at 2026-04-18 03:00 UTC = 2026-04-17 23:00 America/New_York (EDT).
    # All dashboards should bucket this message under 2026-04-17 local,
    # at hour 23, on weekday Fri (4).
    ts = datetime(2026, 4, 18, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 4, 18, 4, 0, tzinfo=timezone.utc)  # still 2026-04-18 00:00 EDT
    s = Session(
        file="/tmp/x", project="p", session_id="x", title=None, model="claude-opus-4-7",
        is_subagent=False,
        messages=[Message(timestamp=ts, usage=TokenUsage(input=10))],
    )
    from prompt_ledger.core.aggregator import aggregate_daily, peak_hour
    daily = aggregate_daily([s])
    assert "2026-04-17" in daily, f"expected local-date bucket 2026-04-17, got {list(daily.keys())}"
    assert peak_hour([s]) == 23
    snap = build_snapshot([s], range_="30d", now=now)
    # UTC date of `now` is 2026-04-18; Eastern date is 2026-04-18; message is on 2026-04-17 Eastern.
    # So today_tokens (local) should be 0, not 10.
    assert snap["today_tokens"] == 0
    # Heatmap cell at local hour=23, weekday=4 (Fri).
    nonzero = [c for c in snap["heatmap"] if c[2] != 0]
    assert nonzero == [[23, 4, 10]], f"unexpected cells: {nonzero}"
