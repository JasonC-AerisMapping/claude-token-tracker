from claude_token_tracker.core.pricing import (
    cache_savings_usd,
    is_known_model,
    normalize_model,
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
