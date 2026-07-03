import pytest

from prompt_ledger.core.pricing import (
    PRICING,
    cache_savings_usd,
    is_known_model,
    normalize_model,
    usage_cost_usd,
)


def test_normalize_strips_claude_prefix_and_date_suffix():
    assert normalize_model("claude-opus-4-7") == "opus-4-7"
    assert normalize_model("claude-sonnet-4-6-20251001") == "sonnet-4-6"
    assert normalize_model("claude-haiku-4-5-20251001") == "haiku-4-5"


def test_normalize_none_returns_unknown():
    assert normalize_model(None) == "unknown"
    assert normalize_model("") == "unknown"


def test_is_known_model_true_for_known():
    assert is_known_model("claude-opus-4-7")
    assert is_known_model("opus-4-7")


def test_is_known_model_false_for_unknown():
    assert not is_known_model("future-model-9000")
    assert not is_known_model(None)


def test_cache_savings_zero_when_no_cache_read():
    assert cache_savings_usd("opus-4-7", cache_read_tokens=0) == 0.0


def test_cache_savings_returns_positive_for_known_model():
    savings = cache_savings_usd("opus-4-7", cache_read_tokens=1_000_000)
    assert savings > 0
    assert savings < 20


def test_cache_savings_zero_for_unknown_model():
    assert cache_savings_usd("future-model-9000", cache_read_tokens=1_000_000) == 0.0


def test_normalize_synthetic_marker_is_unknown():
    assert normalize_model("<synthetic>") == "unknown"


def test_current_models_are_priced():
    for key in ("fable-5", "opus-4-8", "opus-4-7", "sonnet-5", "haiku-4-5"):
        assert key in PRICING, key


def test_cache_write_and_read_ratios():
    # Cache write is 1.25x input; cache read is 0.1x input — for every model.
    for key, p in PRICING.items():
        assert p["cache_write"] == pytest.approx(p["input"] * 1.25), key
        assert p["cache_read"] == pytest.approx(p["input"] * 0.10), key


def test_usage_cost_known_model():
    # 1M of each bucket on opus-4-8: 5 + 25 + 6.25 + 0.50
    cost = usage_cost_usd(
        "claude-opus-4-8",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_create_tokens=1_000_000,
        cache_read_tokens=1_000_000,
    )
    assert cost == pytest.approx(36.75)


def test_usage_cost_unknown_model_is_zero():
    assert usage_cost_usd("future-model-9000", input_tokens=1_000_000) == 0.0
    assert usage_cost_usd(None, output_tokens=500) == 0.0
