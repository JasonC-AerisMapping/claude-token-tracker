"""Per-model token pricing and cache-savings calculation.

Prices are USD per 1M tokens, sourced from Anthropic's public pricing page.
Unknown models are excluded from cache-savings totals — we underreport
rather than guess.
"""
from typing import Optional

# Price per 1M tokens in USD. Keys are the normalized model name.
# Update this table when Anthropic publishes new pricing.
PRICING: dict[str, dict[str, float]] = {
    "opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
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
    """Strip 'claude-' prefix and any '-YYYYMMDD' date suffix."""
    if not model:
        return "unknown"
    name = model.removeprefix("claude-")
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        name = parts[0]
    return name


def is_known_model(model: Optional[str]) -> bool:
    return normalize_model(model) in PRICING


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
