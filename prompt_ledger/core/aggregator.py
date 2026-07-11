"""Rollups and derived metrics over lists of Session objects."""
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

from .models import Message, Session, TokenUsage
from .pricing import (
    cache_savings_usd,
    normalize_model,
    usage_cost_parts_usd,
    usage_cost_usd,
)

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
    """Return {project: TokenUsage} sorted by total descending.

    Includes subagent sessions — their tokens are real usage attributable to
    the project, so excluding them would make project totals sum to less than
    the grand total.
    """
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        buckets[s.project].extend(s.messages)
    totals = {p: _sum_usage(msgs) for p, msgs in buckets.items()}
    return dict(sorted(totals.items(), key=lambda kv: -kv[1].total))


def project_label(project: str) -> str:
    """Short display label: the last 2 path segments, '…/'-prefixed if truncated.

    Fallback only — the decoded project key is lossy (real hyphens in folder
    names become '/'), so prefer labels from derive_project_labels, which uses
    the sessions' real cwd. Kept for projects whose logs carry no cwd.
    """
    parts = project.split("/")
    if len(parts) <= 2:
        return project
    return "…/" + "/".join(parts[-2:])


def _normalize_cwd(path: str) -> str:
    """Normalize a logged cwd for voting/display: one separator style, upper drive."""
    p = path.replace("\\", "/").rstrip("/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].upper() + p[1:]
    return p


def project_real_paths(sessions: Iterable[Session]) -> dict[str, str]:
    """Most common real cwd per project key.

    Main-session cwds outvote subagent ones (subagents may run in worktrees),
    and case/separator variants of the same path are counted together.
    """
    votes: dict[str, Counter] = defaultdict(Counter)
    sub_votes: dict[str, Counter] = defaultdict(Counter)
    for s in sessions:
        if not s.cwd:
            continue
        target = sub_votes if s.is_subagent else votes
        target[s.project][_normalize_cwd(s.cwd)] += 1
    out: dict[str, str] = {}
    for project in set(votes) | set(sub_votes):
        pool = votes.get(project) or sub_votes[project]
        out[project] = pool.most_common(1)[0][0]
    return out


def derive_project_labels(sessions: Iterable[Session]) -> dict[str, str]:
    """Human-readable label per project key.

    Primary source: the real cwd's last path segment ("Merlin",
    "claude-token-tracker"). When two projects share a basename, extend each
    with parent segments until distinct. Projects with no logged cwd fall back
    to project_label() over the decoded key.
    """
    sessions = list(sessions)
    paths = project_real_paths(sessions)
    projects = {s.project for s in sessions}

    def tail(project: str, depth: int) -> str:
        segs = paths[project].split("/")
        return "/".join(segs[-depth:]) if depth < len(segs) else paths[project]

    labels: dict[str, str] = {p: project_label(p) for p in projects if p not in paths}
    depth_of = {p: 1 for p in paths}
    while True:
        candidate = {p: tail(p, d) for p, d in depth_of.items()}
        collided = {
            label for label, n in Counter(candidate.values()).items() if n > 1
        }
        deepen = [
            p for p, label in candidate.items()
            if label in collided and depth_of[p] < len(paths[p].split("/"))
        ]
        if not deepen:
            labels.update(candidate)
            return labels
        for p in deepen:
            depth_of[p] += 1


def aggregate_by_model(sessions: Iterable[Session]) -> dict[str, TokenUsage]:
    """Return {normalized_model: TokenUsage} sorted by total descending.

    Attribution is per message — sessions can mix models (model switches,
    fallbacks), so bucketing a whole session under its first-seen model
    misattributes tokens. Messages without their own model fall back to
    the session's.
    """
    buckets: dict[str, list[Message]] = defaultdict(list)
    for s in sessions:
        for m in s.messages:
            buckets[normalize_model(m.model or s.model)].append(m)
    totals = {m: _sum_usage(msgs) for m, msgs in buckets.items()}
    return dict(sorted(totals.items(), key=lambda kv: -kv[1].total))


def aggregate_series(
    sessions: Iterable[Session], range_: Range, now: datetime
) -> dict[str, TokenUsage]:
    """Ordered {label: TokenUsage} for the usage chart, zero-filled.

    24h → 24 hourly buckets labeled "HH:00" (DISPLAY_TZ wall clock).
    7d / 30d → one bucket per calendar day over the trailing window.
    all → one bucket per day from first activity (capped at 365 days back).

    Zero-filling matters: without it, gaps between active days disappear and
    the x-axis spacing lies about time.
    """
    msgs = [m for s in sessions for m in s.messages]

    # Callers pass range-filtered sessions, so every message here belongs in
    # the chart. Bucket edges don't line up exactly with the filter window
    # (rolling UTC cutoff vs local calendar buckets), so edge messages are
    # clamped into the first/last bucket instead of silently dropped —
    # the chart must always sum to the headline total it sits under.
    if range_ == "24h":
        end_hour = _to_display(now).replace(minute=0, second=0, microsecond=0)
        hours = [end_hour - timedelta(hours=i) for i in range(23, -1, -1)]
        buckets: dict[datetime, list[Message]] = {h: [] for h in hours}
        for m in msgs:
            local = _to_display(m.timestamp).replace(minute=0, second=0, microsecond=0)
            if local not in buckets:
                local = hours[0] if local < hours[0] else hours[-1]
            buckets[local].append(m)
        return {h.strftime("%H:00"): _sum_usage(v) for h, v in buckets.items()}

    end_day = _to_display(now).date()
    if range_ == "all":
        # Chart x-axis is capped at 365 days back; anything older is clamped
        # into the first bucket (none exists in practice — logs start 2026-04).
        first = min(
            (_to_display(m.timestamp).date() for m in msgs), default=end_day
        )
        start_day = max(first, end_day - timedelta(days=365))
    else:
        span_days = {"7d": 6, "30d": 29}[range_]
        start_day = end_day - timedelta(days=span_days)

    start_key = start_day.strftime("%Y-%m-%d")
    end_key = end_day.strftime("%Y-%m-%d")
    day_buckets: dict[str, list[Message]] = defaultdict(list)
    for m in msgs:
        key = _to_display(m.timestamp).strftime("%Y-%m-%d")
        if key < start_key:
            key = start_key
        elif key > end_key:
            key = end_key
        day_buckets[key].append(m)

    out: dict[str, TokenUsage] = {}
    day = start_day
    while day <= end_day:
        key = day.strftime("%Y-%m-%d")
        out[key] = _sum_usage(day_buckets.get(key, []))
        day = day + timedelta(days=1)
    return out


def message_cost_usd(m: Message, fallback_model: str | None) -> float:
    """Estimated API-equivalent cost of one message at its own model and time."""
    return usage_cost_usd(
        m.model or fallback_model,
        input_tokens=m.usage.input,
        output_tokens=m.usage.output,
        cache_create_tokens=m.usage.cache_create,
        cache_read_tokens=m.usage.cache_read,
        cache_create_1h_tokens=m.usage.cache_create_1h,
        at=m.timestamp,
    )


def session_cost_usd(s: Session) -> float:
    """Estimated API-equivalent cost of one session, priced per message.

    Unknown-model messages contribute 0.
    """
    return sum(message_cost_usd(m, s.model) for m in s.messages)


def total_est_cost_usd(sessions: Iterable[Session]) -> float:
    """Sum estimated API-equivalent cost across sessions, skipping unknown models."""
    return sum(session_cost_usd(s) for s in sessions)


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
    """Consecutive active local (DISPLAY_TZ) days ending today or yesterday.

    A quiet morning doesn't zero the streak — it survives until today is
    over without activity.
    """
    active: set[str] = set()
    for s in sessions:
        for m in s.messages:
            active.add(_to_display(m.timestamp).strftime("%Y-%m-%d"))
    day = _to_display(now).date()
    if day.strftime("%Y-%m-%d") not in active:
        day = day - timedelta(days=1)
    count = 0
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
    # Deterministic tie-break: earliest hour wins.
    return max(buckets.items(), key=lambda kv: (kv[1], -kv[0]))[0]


def total_cache_savings_usd(sessions: Iterable[Session]) -> float:
    """Sum cache savings per message, skipping unknown models."""
    total = 0.0
    for s in sessions:
        for m in s.messages:
            total += cache_savings_usd(
                m.model or s.model, m.usage.cache_read, at=m.timestamp
            )
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


def _trend_pct(sessions: Iterable[Session], range_: Range, now: datetime) -> float | None:
    """Change vs the immediately-prior window of the same length.

    Windows match the selected range (24h vs prior 24h, 7d vs prior 7d,
    30d vs prior 30d) so the arrow describes the same number it sits next
    to. None for "all" — there is no prior window.
    """
    deltas = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    window = deltas.get(range_)
    if window is None:
        return None
    this_start = now - window
    prev_start = now - window - window
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
        "project_label": (
            _normalize_cwd(s.cwd).rsplit("/", 1)[-1] if s.cwd else project_label(s.project)
        ),
        "model": normalize_model(s.model),
        "input_tokens": s.input_tokens,
        "output_tokens": s.output_tokens,
        "cache_create_tokens": s.cache_create_tokens,
        "cache_read_tokens": s.cache_read_tokens,
        "total_tokens": s.total_tokens,
        "est_cost_usd": session_cost_usd(s),
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
    all_projects = sorted({s.project for s in all_sessions})
    project_labels = derive_project_labels(all_sessions)
    project_paths = project_real_paths(all_sessions)
    if project:
        all_sessions = [s for s in all_sessions if s.project == project]

    in_range = filter_by_range(all_sessions, range_, now)

    total = sum(s.total_tokens for s in in_range)
    input_sum = sum(s.input_tokens for s in in_range)
    output_sum = sum(s.output_tokens for s in in_range)
    cache_w_sum = sum(s.cache_create_tokens for s in in_range)
    cache_r_sum = sum(s.cache_read_tokens for s in in_range)

    # Cost by token type (donut), priced per message so mixed-model sessions
    # and time-windowed rates land correctly. Unknown models contribute 0,
    # same stance as every other cost figure.
    cost_mix = {"input": 0.0, "output": 0.0, "cache_create": 0.0, "cache_read": 0.0}
    for s in in_range:
        for m in s.messages:
            parts = usage_cost_parts_usd(
                m.model or s.model,
                input_tokens=m.usage.input,
                output_tokens=m.usage.output,
                cache_create_tokens=m.usage.cache_create,
                cache_read_tokens=m.usage.cache_read,
                cache_create_1h_tokens=m.usage.cache_create_1h,
                at=m.timestamp,
            )
            if parts:
                for k, v in parts.items():
                    cost_mix[k] += v

    daily = {d: _usage_to_dict(u) for d, u in aggregate_series(in_range, range_, now).items()}
    projects = {p: _usage_to_dict(u) for p, u in aggregate_by_project(in_range).items()}
    models = {m: _usage_to_dict(u) for m, u in aggregate_by_model(in_range).items()}

    # Per-model and per-project estimated cost (unknown models contribute 0).
    # Model attribution is per message, matching aggregate_by_model.
    model_cost: dict[str, float] = defaultdict(float)
    project_cost: dict[str, float] = defaultdict(float)
    for s in in_range:
        for m in s.messages:
            c = message_cost_usd(m, s.model)
            model_cost[normalize_model(m.model or s.model)] += c
            project_cost[s.project] += c
    for m, d in models.items():
        d["est_cost_usd"] = model_cost.get(m, 0.0)
    for p, d in projects.items():
        d["est_cost_usd"] = project_cost.get(p, 0.0)

    non_sub = sorted(
        [s for s in in_range if not s.is_subagent],
        key=lambda s: s.last_timestamp or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    hour = peak_hour(in_range)

    return {
        "range": range_,
        "project": project,
        "all_projects": all_projects,
        "project_labels": project_labels,
        "project_paths": project_paths,
        "generated_at": now.isoformat(),
        "total_tokens": total,
        "today_tokens": _today_tokens(all_sessions, now),
        "est_cost_usd": total_est_cost_usd(in_range),
        "cache_efficiency": cache_efficiency(in_range),
        "cache_reuse_ratio": cache_reuse_ratio(in_range),
        "cache_savings_usd": total_cache_savings_usd(in_range),
        "streak_days": streak_days(all_sessions, now),
        "peak_hour": hour,
        "active_now_tpm": _active_now_tpm(all_sessions, now),
        "trend_pct": _trend_pct(all_sessions, range_, now),
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
        "cost_mix": cost_mix,
        "sessions": [session_to_dict(s) for s in non_sub[:15]],
    }
