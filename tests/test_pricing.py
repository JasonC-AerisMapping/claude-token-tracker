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
    # Cache write is 1.25x input (5m TTL) / 2x input (1h TTL); cache read is
    # 0.1x input — for every model.
    for key, p in PRICING.items():
        assert p["cache_write"] == pytest.approx(p["input"] * 1.25), key
        assert p["cache_write_1h"] == pytest.approx(p["input"] * 2.00), key
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


def test_usage_cost_splits_5m_and_1h_cache_writes():
    # 1M cache-create tokens on opus-4-8, 400K of them 1h-TTL:
    # 600K * 6.25 + 400K * 10.00 = 3.75 + 4.00 = 7.75 (flat 1.25x says 6.25).
    cost = usage_cost_usd(
        "claude-opus-4-8",
        cache_create_tokens=1_000_000,
        cache_create_1h_tokens=400_000,
    )
    assert cost == pytest.approx(7.75)


def test_usage_cost_clamps_1h_count_to_cache_create_total():
    # Rare log lines report ephemeral_1h > cache_creation_input_tokens (or a
    # zero total). The 1h count must never bill more tokens than exist.
    cost = usage_cost_usd(
        "claude-opus-4-8",
        cache_create_tokens=0,
        cache_create_1h_tokens=500,
    )
    assert cost == 0.0


def test_sonnet5_intro_pricing_applies_by_message_date():
    from datetime import datetime, timezone
    july = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    cost = usage_cost_usd(
        "claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        at=july,
    )
    # Intro rates $2/$10 through 2026-08-31.
    assert cost == pytest.approx(12.00)


def test_sonnet5_standard_pricing_after_intro_window():
    from datetime import datetime, timezone
    september = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    cost = usage_cost_usd(
        "claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        at=september,
    )
    assert cost == pytest.approx(18.00)


def test_no_timestamp_means_standard_rates():
    cost = usage_cost_usd("claude-sonnet-5", input_tokens=1_000_000)
    assert cost == pytest.approx(3.00)


def test_cache_savings_uses_dated_rates():
    from datetime import datetime, timezone
    july = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    # Intro: (2.00 - 0.20) = 1.80 per M vs standard (3.00 - 0.30) = 2.70.
    assert cache_savings_usd("claude-sonnet-5", 1_000_000, at=july) == pytest.approx(1.80)
    assert cache_savings_usd("claude-sonnet-5", 1_000_000) == pytest.approx(2.70)
