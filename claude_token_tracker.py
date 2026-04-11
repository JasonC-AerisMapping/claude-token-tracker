"""
Claude Code Token Usage Tracker
A live desktop dashboard for monitoring Claude Code token consumption.
"""

import json
import os
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import customtkinter as ctk
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

# ── Theme — Vibrant dark mode ────────────────────────────────────────────────
C = {
    # Backgrounds
    "bg":           "#000000",
    "bg_subtle":    "#0a0a0a",
    "card":         "#161625",
    "card_hover":   "#1c1c30",
    "card_border":  "#2a2a45",

    # Accent palette — vibrant, dopamine-inducing
    "electric":     "#6c5ce7",   # Primary purple
    "cyan":         "#00cec9",   # Teal/cyan
    "hot_pink":     "#fd79a8",   # Pink
    "flame":        "#e17055",   # Warm orange
    "sun":          "#ffeaa7",   # Bright yellow
    "mint":         "#55efc4",   # Mint green
    "sky":          "#74b9ff",   # Sky blue
    "lavender":     "#a29bfe",   # Soft purple

    # Token type colors — distinct and vivid
    "input_color":        "#74b9ff",
    "output_color":       "#fd79a8",
    "cache_create_color": "#ffeaa7",
    "cache_read_color":   "#55efc4",

    # Text
    "text":         "#ffffff",
    "text_sec":     "#e0e0e8",
    "text_dim":     "#c0c0d0",

    # Chart
    "chart_bg":     "#12121c",
    "chart_grid":   "#1e1e35",

    # Status
    "live_dot":     "#55efc4",
}

# Card accent colors (left border glow)
CARD_ACCENTS = {
    "total":        "#6c5ce7",
    "today":        "#00cec9",
    "input":        "#74b9ff",
    "output":       "#fd79a8",
    "cache_create": "#ffeaa7",
    "cache_read":   "#55efc4",
    "sessions":     "#a29bfe",
}

REFRESH_INTERVAL_MS = 5000
CLAUDE_DIR = Path.home() / ".claude" / "projects"

# ── Data Parsing ─────────────────────────────────────────────────────────────

def parse_all_sessions():
    sessions = []
    if not CLAUDE_DIR.exists():
        return sessions

    for project_dir in CLAUDE_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        project_name = decode_project_name(project_dir.name)

        for jsonl_file in project_dir.glob("*.jsonl"):
            session = parse_session_file(jsonl_file, project_name)
            if session and session["total_tokens"] > 0:
                sessions.append(session)

        for subdir in project_dir.iterdir():
            if subdir.is_dir() and subdir.name != "memory":
                for sub_jsonl in subdir.glob("**/*.jsonl"):
                    session = parse_session_file(sub_jsonl, project_name, is_subagent=True)
                    if session and session["total_tokens"] > 0:
                        sessions.append(session)

    return sessions


def decode_project_name(dir_name):
    parts = dir_name.split("--")
    if len(parts) > 1:
        path_part = parts[-1]
        for prefix in ["Users-jason-OneDrive-Desktop-", "Users-jason-"]:
            if path_part.startswith(prefix):
                path_part = path_part[len(prefix):]
                break
        return path_part.replace("-", " ") if path_part else dir_name
    return dir_name


def parse_session_file(filepath, project_name, is_subagent=False):
    session = {
        "file": str(filepath),
        "project": project_name,
        "is_subagent": is_subagent,
        "session_id": filepath.stem,
        "title": None,
        "model": None,
        "entrypoint": None,
        "messages": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "first_timestamp": None,
        "last_timestamp": None,
    }

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp")

                if entry_type == "ai-title":
                    session["title"] = entry.get("aiTitle")

                if entry_type == "user":
                    if not session["entrypoint"]:
                        session["entrypoint"] = entry.get("entrypoint", "unknown")

                if entry_type == "assistant":
                    msg = entry.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue

                    if not session["model"]:
                        session["model"] = msg.get("model")

                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cache_create = usage.get("cache_creation_input_tokens", 0)
                    cache_read = usage.get("cache_read_input_tokens", 0)

                    session["input_tokens"] += inp
                    session["output_tokens"] += out
                    session["cache_creation_tokens"] += cache_create
                    session["cache_read_tokens"] += cache_read

                    if timestamp:
                        ts = parse_timestamp(timestamp)
                        if ts:
                            session["messages"].append({
                                "timestamp": ts,
                                "input": inp,
                                "output": out,
                                "cache_create": cache_create,
                                "cache_read": cache_read,
                            })
                            if not session["first_timestamp"] or ts < session["first_timestamp"]:
                                session["first_timestamp"] = ts
                            if not session["last_timestamp"] or ts > session["last_timestamp"]:
                                session["last_timestamp"] = ts

    except Exception:
        return None

    session["total_tokens"] = (
        session["input_tokens"]
        + session["output_tokens"]
        + session["cache_creation_tokens"]
        + session["cache_read_tokens"]
    )
    return session


def parse_timestamp(ts_str):
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def aggregate_daily(sessions):
    daily = defaultdict(lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0})
    for session in sessions:
        for msg in session["messages"]:
            day = msg["timestamp"].strftime("%Y-%m-%d")
            daily[day]["input"] += msg["input"]
            daily[day]["output"] += msg["output"]
            daily[day]["cache_create"] += msg["cache_create"]
            daily[day]["cache_read"] += msg["cache_read"]
    return dict(sorted(daily.items()))


def aggregate_by_project(sessions):
    projects = defaultdict(lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0, "total": 0})
    for s in sessions:
        if not s["is_subagent"]:
            projects[s["project"]]["input"] += s["input_tokens"]
            projects[s["project"]]["output"] += s["output_tokens"]
            projects[s["project"]]["cache_create"] += s["cache_creation_tokens"]
            projects[s["project"]]["cache_read"] += s["cache_read_tokens"]
            projects[s["project"]]["total"] += s["total_tokens"]
    return dict(sorted(projects.items(), key=lambda x: -x[1]["total"]))


def aggregate_by_model(sessions):
    models = defaultdict(int)
    for s in sessions:
        model = s["model"] or "unknown"
        # Clean up model names for display
        display = model.replace("claude-", "").replace("-20251001", "")
        models[display] += s["total_tokens"]
    return dict(sorted(models.items(), key=lambda x: -x[1]))


def format_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ── GUI ──────────────────────────────────────────────────────────────────────

class TokenTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Claude Token Tracker")
        self.geometry("1360x920")
        self.minsize(1100, 750)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=C["bg"])

        self._sessions = []
        self._file_mtimes = {}

        self._build_ui()
        self._refresh_data()
        self._schedule_refresh()

    # ── UI Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=C["bg_subtle"], corner_radius=0, height=56,
                           border_width=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Logo / title area
        title_frame = ctk.CTkFrame(top, fg_color="transparent")
        title_frame.pack(side="left", padx=24)

        ctk.CTkLabel(
            title_frame, text="Claude Token Tracker",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=C["text"],
        ).pack(side="left")

        # Live indicator
        live_frame = ctk.CTkFrame(top, fg_color="transparent")
        live_frame.pack(side="left", padx=(16, 0))

        self._live_dot = ctk.CTkLabel(
            live_frame, text="\u2022", font=ctk.CTkFont(size=18),
            text_color=C["live_dot"],
        )
        self._live_dot.pack(side="left")
        ctk.CTkLabel(
            live_frame, text="LIVE", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C["live_dot"],
        ).pack(side="left", padx=(2, 0))

        self._status_label = ctk.CTkLabel(
            top, text="Scanning...", font=ctk.CTkFont(size=11),
            text_color=C["text_dim"],
        )
        self._status_label.pack(side="right", padx=24)

        # Thin accent line under header
        accent_line = ctk.CTkFrame(self, fg_color=C["electric"], height=2, corner_radius=0)
        accent_line.pack(fill="x")

        # ── Main scrollable body ─────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 12))

        # ── Summary cards ────────────────────────────────────────────────
        self._cards_frame = ctk.CTkFrame(body, fg_color="transparent")
        self._cards_frame.pack(fill="x", pady=(0, 12))

        self._card_widgets = {}
        card_defs = [
            ("total",        "TOTAL TOKENS",  "—", "\u03A3"),
            ("today",        "TODAY",          "—", "\u25C9"),
            ("input",        "INPUT",          "—", "\u2193"),
            ("output",       "OUTPUT",         "—", "\u2191"),
            ("cache_create", "CACHE WRITE",    "—", "\u270E"),
            ("cache_read",   "CACHE READ",     "—", "\u21BB"),
            ("sessions",     "SESSIONS",       "—", "#"),
        ]
        for i, (key, label, val, icon) in enumerate(card_defs):
            accent = CARD_ACCENTS[key]
            card = self._make_card(self._cards_frame, label, val, icon, accent)
            card.grid(row=0, column=i, padx=5, pady=0, sticky="nsew")
            self._cards_frame.columnconfigure(i, weight=1)
            self._card_widgets[key] = card

        # ── Charts 2x2 ──────────────────────────────────────────────────
        charts_frame = ctk.CTkFrame(body, fg_color="transparent")
        charts_frame.pack(fill="both", expand=True, pady=(0, 8))
        charts_frame.rowconfigure(0, weight=1)
        charts_frame.rowconfigure(1, weight=1)
        charts_frame.columnconfigure(0, weight=3)
        charts_frame.columnconfigure(1, weight=2)

        self._daily_fig, self._daily_ax = self._make_chart_figure()
        self._daily_canvas = self._embed_chart(charts_frame, self._daily_fig, 0, 0)

        self._pie_fig, self._pie_ax = self._make_chart_figure()
        self._pie_canvas = self._embed_chart(charts_frame, self._pie_fig, 0, 1)

        self._proj_fig, self._proj_ax = self._make_chart_figure()
        self._proj_canvas = self._embed_chart(charts_frame, self._proj_fig, 1, 0)

        self._model_fig, self._model_ax = self._make_chart_figure()
        self._model_canvas = self._embed_chart(charts_frame, self._model_fig, 1, 1)

        # ── Session list ─────────────────────────────────────────────────
        self._session_frame = ctk.CTkScrollableFrame(
            body, fg_color=C["card"], corner_radius=12, height=175,
            border_width=1, border_color=C["card_border"],
            label_text="  RECENT SESSIONS",
            label_fg_color=C["card"],
            label_text_color=C["text_sec"],
            label_font=ctk.CTkFont(size=11, weight="bold"),
        )
        self._session_frame.pack(fill="x", pady=(0, 0))

    def _make_card(self, parent, label, value, icon, accent_color):
        # Outer card with accent left border effect
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["card_border"])

        # Inner layout
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        # Top row: icon + label
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")

        ctk.CTkLabel(
            top_row, text=icon, font=ctk.CTkFont(size=14),
            text_color=accent_color, width=20,
        ).pack(side="left")

        ctk.CTkLabel(
            top_row, text=label, font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C["text_dim"],
        ).pack(side="left", padx=(6, 0))

        # Value
        val_label = ctk.CTkLabel(
            inner, text=value, font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color="#ffffff", anchor="w",
        )
        val_label.pack(fill="x", pady=(4, 0))

        card._val_label = val_label
        card._accent = accent_color
        return card

    def _update_card(self, key, value):
        self._card_widgets[key]._val_label.configure(text=value)

    def _make_chart_figure(self):
        fig = Figure(figsize=(5, 3), dpi=100)
        fig.patch.set_facecolor(C["bg"])
        fig.patch.set_alpha(0.0)
        ax = fig.add_subplot(111)
        ax.set_facecolor(C["chart_bg"])
        return fig, ax

    def _embed_chart(self, parent, fig, row, col):
        frame = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12,
                             border_width=1, border_color=C["card_border"])
        frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        canvas = FigureCanvasTkAgg(fig, master=frame)
        widget = canvas.get_tk_widget()
        widget.configure(bg=C["card"], highlightthickness=0)
        widget.pack(fill="both", expand=True, padx=8, pady=8)
        return canvas

    def _style_ax(self, ax, title=""):
        ax.set_facecolor(C["chart_bg"])
        ax.set_title(title, color=C["text"], fontsize=12, fontweight="bold", pad=10,
                     fontfamily="Segoe UI", loc="left")
        ax.tick_params(colors=C["text_sec"], labelsize=8, length=0)
        ax.grid(True, axis="y", color=C["chart_grid"], linewidth=0.5, alpha=0.5)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)

    # ── Data Refresh ─────────────────────────────────────────────────────

    def _has_files_changed(self):
        if not CLAUDE_DIR.exists():
            return False
        current = {}
        for f in CLAUDE_DIR.rglob("*.jsonl"):
            try:
                current[str(f)] = f.stat().st_mtime
            except OSError:
                pass
        changed = current != self._file_mtimes
        self._file_mtimes = current
        return changed

    def _refresh_data(self):
        if not self._has_files_changed() and self._sessions:
            return

        self._sessions = parse_all_sessions()
        self._update_summary()
        self._update_charts()
        self._update_session_list()

        n_files = len(self._file_mtimes)
        now = datetime.now().strftime("%H:%M:%S")
        self._status_label.configure(
            text=f"{n_files} sessions tracked  \u00b7  updated {now}"
        )

    def _schedule_refresh(self):
        self._refresh_data()
        # Pulse the live dot
        current = self._live_dot.cget("text_color")
        self._live_dot.configure(text_color=C["bg"] if current == C["live_dot"] else C["live_dot"])
        self.after(REFRESH_INTERVAL_MS, self._schedule_refresh)

    def _update_summary(self):
        total_in = sum(s["input_tokens"] for s in self._sessions)
        total_out = sum(s["output_tokens"] for s in self._sessions)
        total_cc = sum(s["cache_creation_tokens"] for s in self._sessions)
        total_cr = sum(s["cache_read_tokens"] for s in self._sessions)
        total = total_in + total_out + total_cc + total_cr

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_tokens = 0
        for s in self._sessions:
            for m in s["messages"]:
                if m["timestamp"].strftime("%Y-%m-%d") == today_str:
                    today_tokens += m["input"] + m["output"] + m["cache_create"] + m["cache_read"]

        n_sessions = len([s for s in self._sessions if not s["is_subagent"]])

        self._update_card("total", format_tokens(total))
        self._update_card("today", format_tokens(today_tokens))
        self._update_card("input", format_tokens(total_in))
        self._update_card("output", format_tokens(total_out))
        self._update_card("cache_create", format_tokens(total_cc))
        self._update_card("cache_read", format_tokens(total_cr))
        self._update_card("sessions", str(n_sessions))

    def _update_charts(self):
        self._draw_daily_chart()
        self._draw_pie_chart()
        self._draw_project_chart()
        self._draw_model_chart()

    def _no_data(self, ax, canvas):
        ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                color=C["text_dim"], fontsize=13, fontfamily="Segoe UI",
                fontstyle="italic", transform=ax.transAxes)
        canvas.draw_idle()

    def _draw_daily_chart(self):
        ax = self._daily_ax
        ax.clear()
        self._style_ax(ax, "Daily Token Usage")

        daily = aggregate_daily(self._sessions)
        if not daily:
            self._no_data(ax, self._daily_canvas)
            return

        dates = list(daily.keys())
        short_dates = [d[5:] for d in dates]
        inp = [daily[d]["input"] for d in dates]
        out = [daily[d]["output"] for d in dates]
        cc = [daily[d]["cache_create"] for d in dates]
        cr = [daily[d]["cache_read"] for d in dates]

        x = range(len(dates))
        bar_width = 0.6 if len(dates) > 1 else 0.35

        ax.bar(x, inp, width=bar_width, label="Input", color=C["input_color"],
               alpha=0.9, edgecolor="none", zorder=3)
        ax.bar(x, out, width=bar_width, bottom=inp, label="Output", color=C["output_color"],
               alpha=0.9, edgecolor="none", zorder=3)
        bot2 = [a + b for a, b in zip(inp, out)]
        ax.bar(x, cc, width=bar_width, bottom=bot2, label="Cache Write", color=C["cache_create_color"],
               alpha=0.9, edgecolor="none", zorder=3)
        bot3 = [a + b for a, b in zip(bot2, cc)]
        ax.bar(x, cr, width=bar_width, bottom=bot3, label="Cache Read", color=C["cache_read_color"],
               alpha=0.9, edgecolor="none", zorder=3)

        # Total label on top of each bar
        totals = [a + b + c_ + d for a, b, c_, d in zip(inp, out, cc, cr)]
        for i, total in enumerate(totals):
            ax.text(i, total + max(totals) * 0.02, format_tokens(total),
                    ha="center", va="bottom", fontsize=8, color=C["text_sec"],
                    fontweight="bold", zorder=4)

        ax.set_xticks(list(x))
        ax.set_xticklabels(short_dates, rotation=0, ha="center")
        ax.legend(fontsize=7, loc="upper left", framealpha=0.7, edgecolor="none",
                  labelcolor=C["text_sec"], facecolor=C["card"], borderpad=0.8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_tokens(int(v))))
        ax.set_xlim(-0.5, len(dates) - 0.5)
        self._daily_fig.tight_layout()
        self._daily_canvas.draw_idle()

    def _draw_pie_chart(self):
        ax = self._pie_ax
        ax.clear()
        self._style_ax(ax, "Token Breakdown")
        ax.grid(True, axis="x", color=C["chart_grid"], linewidth=0.5, alpha=0.5)
        ax.grid(False, axis="y")

        total_in = sum(s["input_tokens"] for s in self._sessions)
        total_out = sum(s["output_tokens"] for s in self._sessions)
        total_cc = sum(s["cache_creation_tokens"] for s in self._sessions)
        total_cr = sum(s["cache_read_tokens"] for s in self._sessions)

        values = [total_in, total_out, total_cc, total_cr]
        if sum(values) == 0:
            self._no_data(ax, self._pie_canvas)
            return

        labels = ["Input", "Output", "Cache Write", "Cache Read"]
        colors = [C["input_color"], C["output_color"],
                  C["cache_create_color"], C["cache_read_color"]]

        y = range(len(labels))
        bar_h = 0.5
        max_val = max(values)

        bars = ax.barh(y, values, height=bar_h, color=colors,
                       alpha=0.9, edgecolor="none", zorder=3)
        ax.set_yticks(list(y))
        ax.set_yticklabels(labels, fontsize=9, fontweight="bold")
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_tokens(int(v))))

        # Value + percentage labels
        total = sum(values)
        for bar, val in zip(bars, values):
            pct = (val / total * 100) if total > 0 else 0
            ax.text(bar.get_width() + max_val * 0.03, bar.get_y() + bar.get_height() / 2,
                    f"{format_tokens(val)}  ({pct:.1f}%)",
                    va="center", fontsize=8, color=C["text_sec"],
                    fontweight="bold", zorder=4)

        self._pie_fig.tight_layout()
        self._pie_canvas.draw_idle()

    def _draw_project_chart(self):
        ax = self._proj_ax
        ax.clear()
        self._style_ax(ax, "Tokens by Project")
        ax.grid(True, axis="x", color=C["chart_grid"], linewidth=0.5, alpha=0.5)
        ax.grid(False, axis="y")

        projects = aggregate_by_project(self._sessions)
        if not projects:
            self._no_data(ax, self._proj_canvas)
            return

        names = list(projects.keys())[:8]
        short = [n[:22] + "\u2026" if len(n) > 22 else n for n in names]

        # Stacked horizontal bars
        inp_vals = [projects[n]["input"] for n in names]
        out_vals = [projects[n]["output"] for n in names]
        cc_vals = [projects[n]["cache_create"] for n in names]
        cr_vals = [projects[n]["cache_read"] for n in names]
        total_vals = [projects[n]["total"] for n in names]

        y = range(len(names))
        bar_h = 0.55

        ax.barh(y, inp_vals, height=bar_h, color=C["input_color"], alpha=0.9,
                edgecolor="none", label="Input", zorder=3)
        left = inp_vals
        ax.barh(y, out_vals, height=bar_h, left=left, color=C["output_color"],
                alpha=0.9, edgecolor="none", label="Output", zorder=3)
        left = [a + b for a, b in zip(left, out_vals)]
        ax.barh(y, cc_vals, height=bar_h, left=left, color=C["cache_create_color"],
                alpha=0.9, edgecolor="none", label="Cache W", zorder=3)
        left = [a + b for a, b in zip(left, cc_vals)]
        ax.barh(y, cr_vals, height=bar_h, left=left, color=C["cache_read_color"],
                alpha=0.9, edgecolor="none", label="Cache R", zorder=3)

        ax.set_yticks(list(y))
        ax.set_yticklabels(short, fontsize=8)
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_tokens(int(v))))

        # Value labels
        for i, val in enumerate(total_vals):
            ax.text(val + max(total_vals) * 0.02, i, format_tokens(val),
                    va="center", fontsize=8, color=C["text_sec"], fontweight="bold", zorder=4)

        self._proj_fig.tight_layout()
        self._proj_canvas.draw_idle()

    def _draw_model_chart(self):
        ax = self._model_ax
        ax.clear()
        self._style_ax(ax, "Tokens by Model")
        ax.grid(True, axis="x", color=C["chart_grid"], linewidth=0.5, alpha=0.5)
        ax.grid(False, axis="y")

        models = aggregate_by_model(self._sessions)
        if not models:
            self._no_data(ax, self._model_canvas)
            return

        names = list(models.keys())
        vals = [models[n] for n in names]
        model_colors = [C["electric"], C["hot_pink"], C["cyan"],
                        C["flame"], C["lavender"], C["mint"]]

        y = range(len(names))
        bar_h = 0.5

        bars = ax.barh(y, vals, height=bar_h,
                       color=[model_colors[i % len(model_colors)] for i in range(len(names))],
                       alpha=0.9, edgecolor="none", zorder=3)
        ax.set_yticks(list(y))
        ax.set_yticklabels(names, fontsize=9, fontweight="bold")
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_tokens(int(v))))

        for bar, val in zip(bars, vals):
            ax.text(bar.get_width() + max(vals) * 0.02, bar.get_y() + bar.get_height() / 2,
                    format_tokens(val), va="center", fontsize=9, color=C["text_sec"],
                    fontweight="bold", zorder=4)

        self._model_fig.tight_layout()
        self._model_canvas.draw_idle()

    def _update_session_list(self):
        for widget in self._session_frame.winfo_children():
            widget.destroy()

        # Header row
        header = ctk.CTkFrame(self._session_frame, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(4, 6))

        cols = ["Session", "Project", "Model", "Input", "Output", "Cache W", "Cache R", "Total", "When"]
        widths = [210, 130, 110, 75, 75, 75, 75, 80, 130]
        for col, w in zip(cols, widths):
            ctk.CTkLabel(
                header, text=col.upper(), font=ctk.CTkFont(size=9, weight="bold"),
                text_color=C["text_dim"], width=w, anchor="w",
            ).pack(side="left", padx=3)

        # Divider
        ctk.CTkFrame(self._session_frame, fg_color=C["card_border"], height=1).pack(fill="x", padx=8)

        sorted_sessions = sorted(
            [s for s in self._sessions if not s["is_subagent"]],
            key=lambda s: s["last_timestamp"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        for idx, s in enumerate(sorted_sessions[:15]):
            row_color = C["card_hover"] if idx % 2 == 0 else "transparent"
            row = ctk.CTkFrame(self._session_frame, fg_color=row_color, corner_radius=6)
            row.pack(fill="x", padx=4, pady=1)

            title = s["title"] or s["session_id"][:20]
            ts = s["last_timestamp"].strftime("%b %d, %H:%M") if s["last_timestamp"] else "\u2014"
            model_short = (s["model"] or "\u2014").replace("claude-", "").replace("-20251001", "")

            values = [
                (title[:28], C["text"]),
                (s["project"][:18], C["text_sec"]),
                (model_short[:14], C["lavender"]),
                (format_tokens(s["input_tokens"]), C["input_color"]),
                (format_tokens(s["output_tokens"]), C["output_color"]),
                (format_tokens(s["cache_creation_tokens"]), C["cache_create_color"]),
                (format_tokens(s["cache_read_tokens"]), C["cache_read_color"]),
                (format_tokens(s["total_tokens"]), C["text"]),
                (ts, C["text_dim"]),
            ]
            for (val, color), w in zip(values, widths):
                ctk.CTkLabel(
                    row, text=val, font=ctk.CTkFont(size=10),
                    text_color=color, width=w, anchor="w",
                ).pack(side="left", padx=3, pady=4)


def main():
    app = TokenTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
