"""Rollups and derived metrics over lists of Session objects."""
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

from .models import Message, Session, TokenUsage
from .pricing import cache_savings_usd, normalize_model

Range = Literal["24h", "7d", "30d", "all"]
VALID_RANGES: frozenset[str] = frozenset({"24h", "7d", "30d", "all"})

# All calendar-aware rollups (daily buckets, streak day count, peak hour,
# heatmap weekday/hour, "today") are reported in Eastern time so the dashboard
# matches the user's wall clock instead of UTC.
DISPLAY_TZ = ZoneInfo("America/New_York")


def _to_display(dt: datetime) -> datetime:
    """Convert a datetime to DISPLAY_TZ. Naive datetimes are assumed to be UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ)


def _sum_usage(messages: Iterable[Message]) -> TokenUsage:
    inp = out = cw = cr = 0
    for m in messages:
        inp += m.usage.input
        out += m.usage.output
        cw += m.usage.cache_create
        cr += m.usage.cache_read
    return TokenUsage(input=inp, output=out, cache_create=cw, cache_read=cr)


def aggregate_daily(sessions: Iterable[Session]) -> dict[str, TokenUsage]:
    """Return {YYYY-MM-DD: TokenUsage} keyed by local (DISPLAY_TZ) date."""
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        for m in s.messages:
            buckets[_to_display(m.timestamp).strftime("%Y-%m-%d")].append(m)
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


def cache_efficiency(sessions: Iterable[Session]) -> float:
    """Share of billable input tokens served from cache.

    Formula: cache_read / (input + cache_read + cache_create)

    Unlike a naive hit rate that only compares cache_read vs input, this
    includes cache_create in the denominator — those are tokens paid at
    full input price to populate the cache. A pure-cache session (no new
    writes) approaches 1.0; heavy cache churn pushes the number down.
    """
    input_total = 0
    cache_read_total = 0
    cache_create_total = 0
    for s in sessions:
        for m in s.messages:
            input_total += m.usage.input
            cache_read_total += m.usage.cache_read
            cache_create_total += m.usage.cache_create
    denom = input_total + cache_read_total + cache_create_total
    if denom == 0:
        return 0.0
    return cache_read_total / denom


def cache_reuse_ratio(sessions: Iterable[Session]) -> float:
    """Average times each cache-written token is read back: cache_read / cache_create.

    1.0 = break-even (each written token read exactly once).
    Higher = caching is paying off. 0.0 when no cache writes recorded.
    """
    cache_read_total = 0
    cache_create_total = 0
    for s in sessions:
        for m in s.messages:
            cache_read_total += m.usage.cache_read
            cache_create_total += m.usage.cache_create
    if cache_create_total == 0:
        return 0.0
    return cache_read_total / cache_create_total


def streak_days(sessions: Iterable[Session], now: datetime) -> int:
    """Consecutive local (DISPLAY_TZ) days ending today with at least one message."""
    active: set[str] = set()
    for s in sessions:
        for m in s.messages:
            active.add(_to_display(m.timestamp).strftime("%Y-%m-%d"))
    count = 0
    day = _to_display(now).date()
    while day.strftime("%Y-%m-%d") in active:
        count += 1
        day = day - timedelta(days=1)
    return count


def peak_hour(sessions: Iterable[Session]) -> int | None:
    """Local (DISPLAY_TZ) hour-of-day (0-23) with the most tokens. None if no data."""
    buckets: dict[int, int] = defaultdict(int)
    any_data = False
    for s in sessions:
        for m in s.messages:
            buckets[_to_display(m.timestamp).hour] += m.usage.total
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
    # Two disjoint 7-day windows: [now-14d, now-7d) is "previous", [now-7d, now] is "this".
    # filter_by_range only has a lower bound, so compare message-by-message here.
    this_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    this_total = 0
    prev_total = 0
    for s in sessions:
        for m in s.messages:
            if m.timestamp >= this_start and m.timestamp <= now:
                this_total += m.usage.total
            elif m.timestamp >= prev_start and m.timestamp < this_start:
                prev_total += m.usage.total
    if prev_total == 0:
        return 0.0
    return (this_total - prev_total) / prev_total


def _heatmap(sessions: Iterable[Session]) -> list[list[int]]:
    # Cells are emitted as [hour, day_index, total] to match ECharts'
    # [xIndex, yIndex, value] convention (xAxis=hours 0..23, yAxis=days Mon..Sun).
    # Weekday and hour are computed in DISPLAY_TZ so the grid matches the user's
    # wall clock rather than UTC.
    grid: dict[tuple[int, int], int] = defaultdict(int)
    for s in sessions:
        for m in s.messages:
            local = _to_display(m.timestamp)
            # weekday: Mon=0..Sun=6
            grid[(local.weekday(), local.hour)] += m.usage.total
    cells: list[list[int]] = []
    for d in range(7):
        for h in range(24):
            cells.append([h, d, grid.get((d, h), 0)])
    return cells


def _today_tokens(sessions: Iterable[Session], now: datetime) -> int:
    today_str = _to_display(now).strftime("%Y-%m-%d")
    total = 0
    for s in sessions:
        for m in s.messages:
            if _to_display(m.timestamp).strftime("%Y-%m-%d") == today_str:
                total += m.usage.total
    return total


def session_to_dict(s: Session) -> dict:
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
        "cache_efficiency": cache_efficiency(in_range),
        "cache_reuse_ratio": cache_reuse_ratio(in_range),
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
        "sessions": [session_to_dict(s) for s in non_sub[:15]],
    }
