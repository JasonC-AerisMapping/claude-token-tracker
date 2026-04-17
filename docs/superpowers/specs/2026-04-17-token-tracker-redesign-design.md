# Claude Token Tracker — v2 Redesign Design Spec

**Date:** 2026-04-17
**Status:** Approved, ready for implementation plan
**Author:** Jason Cobb (brainstormed with Claude)

## Overview

Rewrite the Claude Token Tracker UI layer and refactor its data pipeline. The current app
(`claude_token_tracker.py`, 745 lines) is a single-file tkinter + matplotlib desktop dashboard.
It works, but the visual language is flat and the data pipeline re-parses every session file on
every refresh.

This spec replaces the UI with an HTML/CSS/JS front-end hosted in a `pywebview` window,
splits the Python into a testable layered architecture, and adds incremental parsing plus
several new derived metrics (cache savings, streak, peak hour).

The final deliverable is still a single Windows `.exe` installed via the existing Inno Setup
installer — no server, no network calls, no behavioral change for end users beyond "it's much
nicer and much faster."

## Goals

1. **Visual overhaul** — glassmorphism aesthetic (frosted cards, gradient numbers, soft color
   glows, smooth animations, real hover states).
2. **Better metrics** — add weekly cache savings ($), streak counter, peak hour, activity
   heatmap, and mini-velocity sparklines on each session row.
3. **Faster refresh** — incremental JSONL parsing, target cold-start < 200 ms on a cache of
   ~500 sessions.
4. **Clean architecture** — separate data-parsing core from the webview bridge from the UI.
5. **Security hardening** — narrow bridge API surface, escape untrusted strings, bundle all
   assets locally (no CDN calls at runtime), content security policy in place.

## Non-goals

- No cloud sync, no account system, no multi-user anything.
- No weekly-quota ring — deferred. Max-plan weekly caps aren't publicly documented as fixed
  numbers; we may add a user-settable cap later.
- No automatic app updater — existing manual Inno-Setup install flow stays.
- No SQLite cache in v2 — can be added later if parse time ever exceeds ~500 ms.
- No mobile, no web, no cross-platform — Windows desktop only (macOS/Linux possible later
  but out of scope for this spec).

## Stack

| Layer | Choice | Why |
|---|---|---|
| Windowing | `pywebview` (uses WebView2 on Windows) | Tiny footprint (~2–5 MB), already available on all Win10/11, simple Python↔JS bridge |
| Frontend markup | Single `index.html` + `styles.css` | No build step |
| Frontend reactivity | Alpine.js (~15 KB, bundled locally) | Lightweight, no toolchain, enough reactivity for a dashboard |
| Charts | Apache ECharts (bundled locally) | Built-in area / heatmap / donut / bar / sparkline; beautiful defaults; easy dark-theme override |
| Packaging | PyInstaller → single `.exe` (unchanged) | Keeps current pipeline |
| Installer | Inno Setup `.iss` (unchanged) | Keeps current install flow |

No `npm`, no `node_modules`, no build step. JS/CSS files are bundled as PyInstaller data files.

## Aesthetic direction

**Glassmorphism dark.** Base background is a deep purple-to-navy linear gradient with three
soft blurred "glow" blobs (purple, pink, cyan) behind content. Cards are frosted glass
(`backdrop-filter: blur(24px)`, `rgba(255,255,255,0.06)` fill, `rgba(255,255,255,0.12)` border,
20 px radius, top-left highlight sheen).

Typography: **Inter** (400/600/700/800) for everything; **JetBrains Mono** for token counts
and model names in the session table. Big hero numbers use white → colored gradient text.

Color palette (CSS custom properties):

```css
--purple: #8b5cf6;  --pink: #ec4899;  --cyan: #06b6d4;
--mint:   #34d399;  --yellow: #fbbf24; --flame: #f97316;
--sky:    #60a5fa;  --text: #ffffff;  --dim: rgba(255,255,255,0.55);
```

Motion: 160 ms ease transitions on hover, pulsing LIVE dot (1.6 s), smooth ECharts series
updates (`notMerge: false`). No animations longer than 300 ms; the app should feel crisp,
not showy.

**Reference mockup:** committed at
`.superpowers/brainstorm/1965-1776461738/content/dashboard-v1.html`. This is the visual truth
for v2 — the implementation should match it pixel-close.

## Dashboard layout

Top-to-bottom rows, all inside a max-width 1500 px centered column:

### Header
App logo (gradient rounded square) + "Claude Token Tracker" + "Max plan" subtitle.
Right side: "Updated HH:MM:SS" + animated LIVE pill.
**Does NOT render the user's email or any PII.**

### Row 1 — Hero cards (4 across)
Each is a frosted glass card with: uppercase label + icon, large gradient value, delta/context
line, sparkline (12 bars showing the last 12 days).

| # | Label | Value | Sparkline color | Notes |
|---|---|---|---|---|
| 1 | Total tokens | all-time sum (e.g. 128.4M) | purple | Delta = % change vs last week |
| 2 | Today | today's sum | pink | Sub-line = active session count |
| 3 | Cache hit rate | `cache_read / (input + cache_read)` | cyan | Delta = change vs last week |
| 4 | Cache savings | USD saved this month, from `pricing.py` | mint | Sub-line = "saved this month" |

### Row 2 — Insight chips (3 across)
Each a small frosted row with a colored icon square + label + value.

| # | Icon | Label | Value example |
|---|---|---|---|
| 1 | 🔥 flame | Streak | "7 days in a row" |
| 2 | ⏰ clock | Peak hour | "2 – 3 PM" |
| 3 | ⚡ bolt | Active now | "2.4K tok / min" or "Idle" |

### Row 3 — Main charts (2 across, 1.6 : 1)

**Left — 30-day token usage (stacked area)**
4-layer stacked area (input / output / cache-write / cache-read) with a dashed white 7-day
moving-average overlay line. Uses ECharts' smooth area type with per-layer linear gradients.
X-axis: dates; Y-axis: formatted with `format_tokens` (K / M suffixes).

**Right — Activity heatmap**
7 rows (Mon–Sun) × 24 columns (0–23 hour). Cell color = bucketed intensity of tokens used
in that slot over the last 30 days. Five bucket levels from "very faint purple" to
"purple-to-pink gradient glow." Hover magnifies cell and shows day/hour + token count.
Bottom-right scale legend.

### Row 4 — Breakdowns (3 across, 0.9 : 1.3 : 1)

1. **Token mix donut** — 4 segments (input / output / cache-W / cache-R), center shows total.
   Side legend with percentage per slice.
2. **Tokens by project** — top 6 stacked horizontal bars, stacked by token type, value label
   at right. Clicking a bar filters the entire dashboard to that project (sets global project
   filter, re-queries all aggregates).
3. **Tokens by model** — up to 6 rows, single-gradient horizontal bar per model, value label
   at right.

### Row 5 — Recent sessions table
Last 15 non-subagent sessions sorted by `last_timestamp` desc. Columns:
`Session title | Project | Model | Input | Output | Velocity sparkline | When`.
Velocity sparkline is an 8-bar mini chart of that session's tokens-per-message over its
lifespan. Row hover highlights the row.

### Top-bar filter (new)
"24h / 7d / 30d / All" segmented control in the header. Changing the selection re-runs
aggregation against the filtered session slice and re-renders every chart + card.

## Architecture (Approach B)

```
claude-token-tracker/
├── app.py                      # entrypoint: create webview, wire bridge
├── claude_token_tracker/
│   ├── __init__.py
│   ├── core/                   # pure Python, no UI, no pywebview imports
│   │   ├── __init__.py
│   │   ├── models.py           # @dataclass Session, Message, TokenUsage, DashboardSnapshot
│   │   ├── parser.py           # incremental JSONL reader
│   │   ├── aggregator.py       # daily / hourly / project / model rollups + derived metrics
│   │   └── pricing.py          # per-model $/token, cache-savings calc
│   ├── bridge/
│   │   ├── __init__.py
│   │   └── api.py              # pywebview JS bridge — ONLY surface JS can call
│   └── ui/                     # bundled via PyInstaller `datas`
│       ├── index.html
│       ├── styles.css
│       ├── app.js              # Alpine components + ECharts setup, talks to bridge
│       └── vendor/
│           ├── alpine.min.js
│           └── echarts.min.js
├── tests/
│   ├── test_parser.py
│   ├── test_aggregator.py
│   └── test_pricing.py
├── requirements.txt            # customtkinter → pywebview
├── ClaudeTokenTracker.spec     # PyInstaller config, updated to bundle ui/ as datas
├── installer.iss               # unchanged
└── run_tracker.bat             # unchanged
```

### Data flow

1. `app.py` boots. Creates `core.parser.IncrementalScanner` and `bridge.api.Api`.
2. `webview.create_window(..., js_api=api)` opens the WebView2 window pointing at
   `ui/index.html`.
3. `app.js` on load calls `window.pywebview.api.get_dashboard({range: '30d'})`.
4. Bridge method runs `scanner.scan()` (incremental — only new bytes), then
   `aggregator.build_snapshot(sessions, range)`, returns a `DashboardSnapshot` dict.
5. JS distributes snapshot to Alpine state; each chart component reads its slice and updates
   ECharts instance with `setOption(opts, {notMerge: false})` so transitions animate.
6. A 5-second `setInterval` triggers `get_dashboard()` again. The bridge debounces: if no
   file mtime has changed, it returns the cached snapshot unchanged.

### Incremental parsing (core/parser.py)

The speed win. Current code re-reads every JSONL file on every refresh. JSONL files are
append-only, so we:

1. Keep a `dict[Path, FileState]` where `FileState = (last_offset, last_mtime, parsed_session)`.
2. On each scan: `stat()` each file; if `mtime` unchanged, reuse cached `Session`.
3. If changed: `seek(last_offset)`, read only new bytes, append new messages to the cached
   `Session`, update its aggregates, update `last_offset`.
4. New files: full parse from zero, add to cache.
5. Deleted files: remove from cache.

Expected: first scan is proportional to total bytes; subsequent scans are
proportional to bytes added since last scan (usually kilobytes). Cold start target < 200 ms
for ~500 cached sessions.

### Bridge API surface (bridge/api.py)

Only these methods are exposed to JS. Everything is read-only except `export_csv` which uses
pywebview's native save-file dialog (no raw filesystem access from JS).

```python
class Api:
    def get_dashboard(self, range: str = "30d", project: str | None = None) -> dict: ...
    def get_session(self, session_id: str) -> dict: ...
    def open_session_folder(self, session_id: str) -> None: ...    # opens in Explorer
    def export_csv(self) -> bool: ...                               # shows save dialog, writes
    def get_app_info(self) -> dict:                                 # version, data source path
```

`range` is validated against a whitelist `{"24h", "7d", "30d", "all"}`. `project` and
`session_id` are validated against currently-known values — anything unknown returns empty.
No path parameters, no shell-exec, no arbitrary file I/O.

### Derived metrics (core/aggregator.py)

| Metric | Formula |
|---|---|
| `cache_hit_rate` | `sum(cache_read) / sum(input + cache_read)` over selected range |
| `cache_savings_usd` | `(cache_read_tokens * input_price) − (cache_read_tokens * cache_read_price)` per model, summed |
| `streak_days` | Count of consecutive days (ending today) with ≥ 1 message |
| `peak_hour` | Hour-of-day bucket with max total tokens over the selected range; displayed as a 1-hour window e.g. "2 – 3 PM" |
| `active_now_tpm` | `sum(tokens) / minutes` across messages in last 5 min; null if empty |
| `weekly_trend_pct` | `(this_week_total − prev_week_total) / prev_week_total` |

Pricing lives in `core/pricing.py` as a plain dict, sourced from Anthropic's public pricing
page. Unknown models are excluded from the cache-savings total (their tokens don't contribute
to the dollar figure). The savings card shows a small "?" badge if any sessions were
excluded, with a tooltip listing unknown model IDs. Better to underreport than lie.

## Performance

**Target: every UI refresh < 100 ms end-to-end after the first scan.**

| Optimization | Impact |
|---|---|
| Incremental JSONL parsing | 10–100× faster refresh on steady-state |
| Debounced mtime check (wait 500 ms after last change) | Avoids thrashing during active sessions |
| Single aggregation pass per refresh | Today's code aggregates inside each chart function |
| ECharts animated updates (`notMerge: false`) | No teardown/rebuild on refresh |
| Parser runs on a worker thread | UI stays responsive during rescans |
| Lazy session rows (virtualize beyond 15) | Big cache doesn't freeze the table |

## Security

**Threat model:** single-user local desktop app. The user is trusted. The JSONL files are
written by Claude Code and might contain attacker-crafted content if a user runs a malicious
MCP server, hook, or plugin that injects crafted titles / project names / tool output into
the transcript. We treat every JSONL string as untrusted for display purposes.

### Controls

1. **Narrow bridge** — only the methods listed in "Bridge API surface" are exposed. No
   `eval`, no raw path params, no shell methods.
2. **Input validation** — `range` whitelisted; `session_id` and `project` must match currently
   known values or return empty; `export_csv` uses the native save dialog, never accepts a
   raw path from JS.
3. **Path whitelist** — parser rejects any file outside `~/.claude/projects`.
4. **HTML escaping** — Alpine `x-text` escapes by default; ECharts tooltip/axis formatters
   wrap user strings through a helper that escapes `<>&"'`.
5. **CSP** — `<meta http-equiv="Content-Security-Policy" content="default-src 'self';
   style-src 'self' 'unsafe-inline'; connect-src 'none'; img-src 'self' data:;">` — no remote
   fetch, no inline scripts.
6. **Local-only assets** — Alpine and ECharts bundled in `ui/vendor/`. Zero CDN calls at
   runtime. Protects against supply-chain swaps and works offline.
7. **No PII in UI / logs** — per standing rule. Header shows plan tier only, not email.
8. **Least privilege install** — keep `PrivilegesRequired=lowest` in Inno Setup.
9. **Safe decode** — remove the hardcoded `Users-jason-*` project-name decoder. Replace with
   a generic "take the last `--`-separated component, replace `-` with `/`" that doesn't bake
   the current user's home path into source.

## Build & distribution

- `ClaudeTokenTracker.spec` gets `datas=[('claude_token_tracker/ui', 'claude_token_tracker/ui')]`
  so the HTML/CSS/JS are bundled into the `.exe`.
- `requirements.txt`: `pywebview` replaces `customtkinter` and `matplotlib` (both go away).
- `run_tracker.bat`: `pip install` list updated to reflect new deps.
- `installer.iss`: no changes — it still ships a single `.exe`.

Expected bundle size: comparable to current (~30–50 MB PyInstaller one-file), possibly
smaller now that matplotlib is gone.

## Testing

`core/` is pure Python and gets the bulk of the tests:

- `test_parser.py` — incremental parsing correctness, offset tracking, file-deleted handling,
  malformed JSON tolerance, path-whitelist rejection.
- `test_aggregator.py` — rollups, streak calculation across midnight, peak-hour tie-breaks,
  range filtering.
- `test_pricing.py` — cache-savings math, unknown-model fallback, currency formatting.

The UI layer has no automated tests in v2 — manual smoke-test via `run_tracker.bat`.

## Open questions / deferred

- **Weekly quota ring** — deferred. Needs user-entered cap. Add after initial release if
  behavior suggests it.
- **Cross-platform (macOS / Linux)** — pywebview supports both but out of scope.
- **SQLite cache** — only if in-memory parsing ever exceeds 500 ms.
- **Auto-updater** — deferred.
- **Click-to-filter project bar** — specified in the mockup but low priority; if it slips
  from v2, ship without it.

## Acceptance criteria

Ship when all of these are true:

1. Dashboard renders the 5 rows specified, with every widget listed.
2. Visuals match the committed mockup at
   `.superpowers/brainstorm/1965-1776461738/content/dashboard-v1.html` (a reasonable person
   would say "yes, that's the same design").
3. Cold-start cache of 500 sessions parses in < 200 ms.
4. Refresh with no file changes is a no-op (< 10 ms).
5. Time-range filter updates every widget in < 100 ms.
6. No CDN/network calls at runtime (verified by disabling network and running).
7. All listed `core/` tests pass.
8. `PyInstaller` produces a working single-file `.exe`.
9. Email/PII is not rendered anywhere in the UI.
10. CSP header is present; Alpine renders user strings via `x-text`; ECharts tooltips escape
    user strings.
