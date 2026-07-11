# Prompt Ledger Metrics Audit — Verdict Report

**Date:** 2026-07-10 · **App:** Prompt Ledger v2.3.0 (dist EXE = current source) · **Corpus:** 388 JSONL files, 880.9M deduped tokens, frozen at 2026-07-11T00:03:40Z

**Method:** Independent from-scratch recompute of every surfaced metric, diffed against the app's real pipeline (`Api.get_dashboard`) across 20 snapshots (4 ranges × 5 project filters). Tier-1 result: **0 mismatches** — the recompute reproduces the app exactly, so all deltas below are trustworthy. Pricing verified against live Anthropic docs 2026-07-10.

## Headline verdicts (range = all, all projects)

| Metric (UI label) | App shows | Truth | Verdict | Cause |
|---|---|---|---|---|
| Total tokens | 880,869,403 | same | ⚠️ LEGIT number, MISLEADING framing | 94.8% is cache reads (90.6% on 24h). Arithmetic & dedup are correct. |
| Today | (validated exact) | same | ✅ LEGIT | Eastern bucketing matches system TZ |
| Est. API cost | $1,192.03 | **$1,288.78** | ❌ BIASED −7.5% | D12: 1h cache writes at 1.25× not 2× (−$107.67) · D1: first-model attribution (+$0.31) · D2: sonnet-5 intro pricing not applied (+$10.61) |
| Cache savings | $5,530.09 | ~$5,477.86 | ⚠️ BIASED +~1% | D1 attribution +$24.55 · sonnet-5 intro rates +~$27.68 |
| Cache efficiency / reuse ratio | (exact) | same | ✅ LEGIT | Sound definition, correct math |
| Streak | 2 days | 2 days | ⚠️ Definition quirk | Reads 0 every morning until first message (not triggered today) |
| Peak hour | (exact) | same | ✅ LEGIT | Tie-break nondeterministic (cosmetic) |
| Active now | (exact) | same | ✅ LEGIT | |
| "vs last week" arrow | +58.2% (all ranges) | 24h: **+827%** · 30d: **+871%** | ❌ MISLEADING | Always fixed 7d-vs-prior-7d regardless of selected range |
| Token usage chart (24h) | drops 5,257,771 tokens | chart should equal hero | ❌ BROKEN | In-window messages outside the 24 Eastern hourly slots silently dropped (~5.5% of the day) |
| Token usage chart (7d) | drops 2,397,109 tokens | 〃 | ❌ BROKEN | Same Eastern-date edge at window start (~0.7%) |
| By model | fable-5 435.9M / opus-4-8 168.2M / unknown 135,847 | fable-5 430.1M / opus-4-8 175.0M / unknown 0 | ❌ BIASED | D1: whole session attributed to first-seen model; sessions whose first line is `<synthetic>` dump real tokens into "unknown" at $0 |
| Per-model cost | fable-5 $809.90 | fable-5 $882.23 | ❌ BIASED | D1 + D12 |
| By project | (exact tokens) | same | ✅ LEGIT tokens; costs inherit D1/D12 |
| Cost mix donut | (session-level parts) | message-level | ⚠️ BIASED | Inherits D1/D12 |
| Sessions table | (exact) | same | ✅ LEGIT tokens; per-session cost inherits D1 |
| CSV export | (session token sums) | same | ✅ LEGIT |

## What was cleared

- **The v2.3.0 dedup is correct.** 14,572 raw usage lines → 5,606 real messages (the old 2.6× overcount is properly fixed; message.id↔requestId are 1:1).
- **No subagent double counting.** All 273 agent-*.jsonl files' usage appears nowhere else (0 message-id overlap with parents; 0 sidechain usage lines outside subagents\). Counting them is correct — that usage is real.
- **No dropped usage.** Zero timestamp-less assistant lines in the corpus (D6 dead). Zero malformed JSON. `<synthetic>` lines carry no real tokens (D3 dead — the app's phantom "unknown" bucket is purely a D1 artifact).
- **Timezone**: hardcoded Eastern happens to match this machine. Portability caveat only.

## Anomalies (noted, negligible)

- 6 usage lines with `cache_creation_input_tokens=0` but nonzero ephemeral breakdown (~2.6K tokens) → C2 formula clamps.
- 1 message flipped model mid-stream (fable-5 → opus-4-8) → dedup takes the final model.

## Fix list (Phase C)

C1 per-message model attribution · C2 1h-cache-write @2× + dated sonnet-5 intro rates (clamped) · C3 range-matched trend · C4 chart/hero parity (clamp edge messages into first bucket, all ranges) · C5 labels (cache-read subtitle, streak-through-yesterday, deterministic peak hour, range-exempt chips) · C7 v2.4.0. D10: rebuild/remove stale v2.2.0 installer.
