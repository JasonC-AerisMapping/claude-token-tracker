"""Rollups and derived metrics over lists of Session objects."""
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from .models import Message, Session, TokenUsage
from .pricing import cache_savings_usd, normalize_model

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
