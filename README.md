# Prompt Ledger

A local desktop dashboard that reads your Claude Code session logs and shows how many tokens each project, model, and session has consumed.

**For users of [Claude Code](https://claude.com/claude-code), Anthropic's CLI coding tool.** This is a local viewer for the session logs Claude Code already writes to your machine. It is not affiliated with or endorsed by Anthropic.

![Platform: Windows | macOS](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![Version 2.2.0](https://img.shields.io/badge/version-2.2.0-green)

---

## What it does

Claude Code stores a JSONL log of every session under `~/.claude/projects/`. Prompt Ledger parses those logs and renders:

- **Hero metrics** — total tokens, today's tokens, estimated API-equivalent cost, and cache savings for the selected range (24h / 7d / 30d / all)
- **Est. API cost** — what the usage would have cost at public API rates (per range, per model, per project, per session); the number that shows what a Claude subscription is worth
- **Usage chart** — stacked by token type; hourly buckets on the 24h view, zero-filled daily buckets elsewhere, with a 7-day moving average
- **Activity heatmap** — day-of-week × hour-of-day, local wall clock
- **Model & project breakdowns** — input / output / cache-create / cache-read split, with cost in the tooltips; subagent usage is attributed to its project
- **Project filter** — scope the whole dashboard to one project
- **Recent sessions** — session title, model, tokens, cost, and a velocity sparkline; click a row to open that session's log folder
- **CSV export** — full session table to a CSV file of your choice

All data stays on your machine. The app has `connect-src 'none'` in its CSP — it makes no network calls.

---

## Installation

### Windows

1. Download `PromptLedger_Setup.exe` from the [latest release](https://github.com/JasonC-AerisMapping/claude-token-tracker/releases/latest).
2. Run it. Installs per-user (no admin prompt).
3. Launch **Prompt Ledger** from the Start menu.

Windows SmartScreen may warn on first run because the binary is not code-signed. Click **More info → Run anyway**.

### macOS

1. Download `PromptLedger.dmg` from the [latest release](https://github.com/JasonC-AerisMapping/claude-token-tracker/releases/latest).
2. Open the DMG and drag **Prompt Ledger** to Applications.
3. First launch: right-click the app → **Open** (macOS Gatekeeper requires this for unsigned apps; one-time).

---

## Running from source

Requires Python 3.12.

```bash
pip install -r requirements.txt
python app.py
```

On Windows you can double-click `run_tracker.bat`.

To build a standalone executable locally:

```bash
pyinstaller PromptLedger.spec --noconfirm
```

Output: `dist/PromptLedger.exe` (Windows) or `dist/PromptLedger` (macOS).

---

## How it works

- `prompt_ledger/core/parser.py` incrementally reads every `*.jsonl` under `~/.claude/projects/`. Only new bytes are parsed on rescan.
- `prompt_ledger/core/aggregator.py` groups messages into sessions, rolls up token totals, and produces the dashboard snapshot.
- `prompt_ledger/bridge/api.py` is the pywebview `js_api` surface. JavaScript can only call whitelisted methods — no arbitrary filesystem access.
- `prompt_ledger/ui/` is an Alpine.js + ECharts single-page UI loaded via `file://`. No CDN, no network.

43 unit tests cover parsing, aggregation, the bridge API, pricing, and model resolution. Run with `pytest`.

---

## Disclaimer

Prompt Ledger depends on the structure of the JSONL files Claude Code writes to `~/.claude/projects/`. That format is undocumented and internal to Anthropic. **If Anthropic changes the log format, the app may stop reporting correctly until it is updated.**

This is a third-party tool. It is **not** made by, supported by, or affiliated with Anthropic. "Claude" and "Claude Code" are trademarks of Anthropic PBC.

Pricing estimates shown in the UI are approximate and reflect publicly posted Anthropic rates at the time of release. They may lag real pricing.

---

## Privacy

- No telemetry, no analytics, no auto-update phone-home.
- No network requests of any kind (`connect-src 'none'` enforced by CSP).
- All reading happens locally against `~/.claude/projects/`. Nothing is written outside of a CSV export you explicitly trigger.

---

## License

See [LICENSE](LICENSE).
