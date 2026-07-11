"""Per-model token pricing, estimated API-equivalent cost, and cache savings.

Prices are USD per 1M tokens, sourced from Anthropic's public pricing
(verified 2026-07-10 against platform.claude.com). Cache writes bill at
1.25x input for the default 5-minute TTL and 2x input for the 1-hour TTL;
cache reads at 0.1x input. Sonnet 5 has introductory pricing through
2026-08-31, applied by message timestamp via PRICING_OVERRIDES. Unknown
models are excluded from cost and savings totals — we underreport rather
than guess.
"""
from datetime import date, datetime, timezone
from typing import Optional

# Price per 1M tokens in USD. Keys are the normalized model name.
# Update this table when Anthropic publishes new pricing.
PRICING: dict[str, dict[str, float]] = {
    "fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_write": 12.50,
        "cache_write_1h": 20.00,
        "cache_read": 1.00,
    },
    "opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_write_1h": 10.00,
        "cache_read": 0.50,
    },
    "opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_write_1h": 10.00,
        "cache_read": 0.50,
    },
    "sonnet-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_write_1h": 6.00,
        "cache_read": 0.30,
    },
    "sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_write_1h": 6.00,
        "cache_read": 0.30,
    },
    "haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_write_1h": 2.00,
        "cache_read": 0.10,
    },
}

# Time-windowed rate overrides, applied by message timestamp (UTC date).
# Each entry: model key -> (last day the override applies, rates).
# Sonnet 5 introductory pricing: $2/$10 through 2026-08-31.
PRICING_OVERRIDES: dict[str, tuple[date, dict[str, float]]] = {
    "sonnet-5": (
        date(2026, 8, 31),
        {
            "input": 2.00,
            "output": 10.00,
            "cache_write": 2.50,
            "cache_write_1h": 4.00,
            "cache_read": 0.20,
        },
    ),
}


def normalize_model(model: Optional[str]) -> str:
    """Strip 'claude-' prefix and any '-YYYYMMDD' date suffix.

    Non-model markers like '<synthetic>' (error placeholders in the logs)
    collapse to 'unknown'.
    """
    if not model or model.startswith("<"):
        return "unknown"
    name = model.removeprefix("claude-")
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        name = parts[0]
    return name


def is_known_model(model: Optional[str]) -> bool:
    return normalize_model(model) in PRICING


def rates_for(model: Optional[str], at: Optional[datetime] = None) -> Optional[dict[str, float]]:
    """Rate table for a model at a point in time. None for unknown models.

    ``at`` selects time-windowed overrides (e.g. Sonnet 5 intro pricing);
    without it, standard rates apply.
    """
    key = normalize_model(model)
    base = PRICING.get(key)
    if base is None:
        return None
    if at is not None and key in PRICING_OVERRIDES:
        until, rates = PRICING_OVERRIDES[key]
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at.astimezone(timezone.utc).date() <= until:
            return rates
    return base


def usage_cost_usd(
    model: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_create_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_create_1h_tokens: int = 0,
    at: Optional[datetime] = None,
) -> float:
    """Estimated USD this usage would cost at public API rates.

    Returns 0.0 for unknown models (we underreport rather than guess).
    1h-TTL cache writes (a sub-count of cache_create_tokens) bill at 2x
    input instead of 1.25x.
    """
    p = rates_for(model, at)
    if p is None:
        return 0.0
    # Clamp: rare log lines report an ephemeral_1h count with a zero total.
    cc_1h = min(cache_create_1h_tokens, cache_create_tokens)
    cc_5m = cache_create_tokens - cc_1h
    return (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cc_5m * p["cache_write"]
        + cc_1h * p["cache_write_1h"]
        + cache_read_tokens * p["cache_read"]
    ) / 1_000_000


def usage_cost_parts_usd(
    model: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_create_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_create_1h_tokens: int = 0,
    at: Optional[datetime] = None,
) -> Optional[dict[str, float]]:
    """Estimated USD per token type at public API rates.

    Returns None for unknown models (we underreport rather than guess).
    """
    p = rates_for(model, at)
    if p is None:
        return None
    cc_1h = min(cache_create_1h_tokens, cache_create_tokens)
    cc_5m = cache_create_tokens - cc_1h
    return {
        "input": input_tokens * p["input"] / 1_000_000,
        "output": output_tokens * p["output"] / 1_000_000,
        "cache_create": (cc_5m * p["cache_write"] + cc_1h * p["cache_write_1h"]) / 1_000_000,
        "cache_read": cache_read_tokens * p["cache_read"] / 1_000_000,
    }


def cache_savings_usd(
    model: Optional[str],
    cache_read_tokens: int,
    at: Optional[datetime] = None,
) -> float:
    """USD saved by using cache_read instead of regular input pricing.

    Returns 0.0 for unknown models (we underreport rather than guess).
    """
    p = rates_for(model, at)
    if p is None:
        return 0.0
    full_cost = (cache_read_tokens / 1_000_000) * p["input"]
    actual_cost = (cache_read_tokens / 1_000_000) * p["cache_read"]
    return full_cost - actual_cost
