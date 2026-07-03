"""Per-model token pricing, estimated API-equivalent cost, and cache savings.

Prices are USD per 1M tokens, sourced from Anthropic's public pricing
(verified 2026-07-03). Cache write is billed at 1.25x input (5-minute TTL);
cache read at 0.1x input. Unknown models are excluded from cost and savings
totals — we underreport rather than guess.
"""
from typing import Optional

# Price per 1M tokens in USD. Keys are the normalized model name.
# Update this table when Anthropic publishes new pricing.
PRICING: dict[str, dict[str, float]] = {
    "fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_write": 12.50,
        "cache_read": 1.00,
    },
    "opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    # Sonnet 5 has intro pricing ($2/$10) through 2026-08-31; standard rates here.
    "sonnet-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
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


def usage_cost_usd(
    model: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_create_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimated USD this usage would cost at public API rates.

    Returns 0.0 for unknown models (we underreport rather than guess).
    """
    key = normalize_model(model)
    if key not in PRICING:
        return 0.0
    p = PRICING[key]
    return (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_create_tokens * p["cache_write"]
        + cache_read_tokens * p["cache_read"]
    ) / 1_000_000


def cache_savings_usd(model: Optional[str], cache_read_tokens: int) -> float:
    """USD saved by using cache_read instead of regular input pricing.

    Returns 0.0 for unknown models (we underreport rather than guess).
    """
    key = normalize_model(model)
    if key not in PRICING:
        return 0.0
    prices = PRICING[key]
    full_cost = (cache_read_tokens / 1_000_000) * prices["input"]
    actual_cost = (cache_read_tokens / 1_000_000) * prices["cache_read"]
    return full_cost - actual_cost
