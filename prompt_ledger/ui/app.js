/* global Alpine, echarts, pywebview */

function dashboard() {
  return {
    range: "30d",
    data: {},
    updatedAt: "—",
    charts: { daily: null, heatmap: null, donut: null, projects: null, models: null },

    async init() {
      this._initCharts();
      this._setupSparkTips();
      this._setupDailyOverlay();
      window.addEventListener("resize", () => this._resizeCharts());
      const boot = () => {
        this.refresh();
        setInterval(() => this.refresh(), 5000);
      };
      if (window.pywebview?.api?.get_dashboard) {
        boot();
      } else {
        window.addEventListener("pywebviewready", boot, { once: true });
      }
    },

    _setupDailyOverlay() {
      const host = document.getElementById("chart-daily");
      if (!host) return;
      host.style.position = "relative";
      const tip = document.createElement("div");
      tip.className = "daily-tip";
      host.appendChild(tip);
      const guide = document.createElement("div");
      guide.className = "daily-guide";
      host.appendChild(guide);

      const gridLeft = 40, gridRight = 16, gridTop = 20, gridBottom = 30;
      const colors = { input: "#60a5fa", output: "#ec4899", cache_create: "#fbbf24", cache_read: "#34d399" };
      const fmt = (n) => Math.round(Number(n) || 0).toLocaleString("en-US");

      const buildRow = (color, label, value, cls) => {
        const line = document.createElement("div");
        line.className = cls || "daily-tip-row";
        const left = document.createElement("span");
        if (color) {
          const dot = document.createElement("span");
          dot.className = "dot";
          dot.style.background = color;
          left.appendChild(dot);
        }
        left.appendChild(document.createTextNode(label));
        const val = document.createElement("span");
        val.className = "val";
        val.textContent = fmt(value);
        line.appendChild(left);
        line.appendChild(val);
        return line;
      };

      host.addEventListener("mousemove", (e) => {
        const daily = this.data.daily || {};
        const dates = Object.keys(daily);
        if (dates.length === 0) { tip.classList.remove("visible"); guide.classList.remove("visible"); return; }
        const rect = host.getBoundingClientRect();
        const plotWidth = rect.width - gridLeft - gridRight;
        const x = e.clientX - rect.left - gridLeft;
        if (x < 0 || x > plotWidth) { tip.classList.remove("visible"); guide.classList.remove("visible"); return; }
        const step = dates.length > 1 ? plotWidth / (dates.length - 1) : plotWidth;
        const idx = Math.max(0, Math.min(dates.length - 1, Math.round(x / step)));
        const date = dates[idx];
        const r = daily[date] || {};
        const total = (r.input || 0) + (r.output || 0) + (r.cache_create || 0) + (r.cache_read || 0);

        while (tip.firstChild) tip.removeChild(tip.firstChild);
        const head = document.createElement("div");
        head.className = "daily-tip-head";
        head.textContent = date;
        tip.appendChild(head);
        tip.appendChild(buildRow(colors.input, "Input", r.input || 0));
        tip.appendChild(buildRow(colors.output, "Output", r.output || 0));
        tip.appendChild(buildRow(colors.cache_create, "Cache write", r.cache_create || 0));
        tip.appendChild(buildRow(colors.cache_read, "Cache read", r.cache_read || 0));
        tip.appendChild(buildRow(null, "Total", total, "daily-tip-total"));
        tip.classList.add("visible");

        const pointX = gridLeft + idx * step;
        guide.style.left = pointX + "px";
        guide.style.top = gridTop + "px";
        guide.style.height = (rect.height - gridTop - gridBottom) + "px";
        guide.classList.add("visible");

        const tipW = tip.offsetWidth;
        let left = pointX - tipW / 2;
        left = Math.max(4, Math.min(rect.width - tipW - 4, left));
        tip.style.left = left + "px";
        tip.style.top = (gridTop + 4) + "px";
      });

      host.addEventListener("mouseleave", () => {
        tip.classList.remove("visible");
        guide.classList.remove("visible");
      });
    },

    _setupSparkTips() {
      const getTip = (container) => {
        let tip = container.querySelector(":scope > .spark-tip");
        if (!tip) {
          tip = document.createElement("div");
          tip.className = "spark-tip";
          container.appendChild(tip);
        }
        return tip;
      };
      document.addEventListener("mouseover", (e) => {
        const bar = e.target.closest(".sparkline span[data-tip]");
        if (!bar) return;
        const container = bar.parentElement;
        if (!container) return;
        const tip = getTip(container);
        tip.textContent = bar.getAttribute("data-tip");
        tip.classList.add("visible");
        const barRect = bar.getBoundingClientRect();
        const cRect = container.getBoundingClientRect();
        const tipWidth = tip.offsetWidth;
        const barCenter = (barRect.left + barRect.right) / 2 - cRect.left;
        let left = barCenter - tipWidth / 2;
        left = Math.max(0, Math.min(cRect.width - tipWidth, left));
        tip.style.left = left + "px";
      });
      document.addEventListener("mouseout", (e) => {
        const bar = e.target.closest(".sparkline span[data-tip]");
        if (!bar) return;
        const container = bar.parentElement;
        if (!container) return;
        const tip = container.querySelector(":scope > .spark-tip");
        if (tip) tip.classList.remove("visible");
      });
    },

    async refresh() {
      if (!window.pywebview?.api?.get_dashboard) {
        console.warn("pywebview bridge not ready");
        return;
      }
      try {
        const snap = await window.pywebview.api.get_dashboard(this.range, null);
        if (snap && !snap.error) {
          this.data = snap;
          this.updatedAt = new Date().toLocaleTimeString([], { hour12: false });
          this._renderCharts();
        } else {
          console.warn("dashboard returned error or empty:", snap);
        }
      } catch (err) {
        console.error("refresh failed:", err);
      }
    },

    setRange(r) {
      this.range = r;
      this.refresh();
    },

    fmt(n) {
      if (n == null) return "—";
      if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
      if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
      return String(n);
    },
    fmtExact(n) {
      if (n == null) return "—";
      return Math.round(n).toLocaleString("en-US");
    },
    _tooltipRow(color, name, value) {
      const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px;vertical-align:middle"></span>`;
      return `<div style="display:flex;justify-content:space-between;gap:16px;font-size:12px;line-height:1.6"><span>${dot}${name}</span><span style="font-family:'Cascadia Mono',Consolas,ui-monospace,monospace;font-weight:600">${this.fmtExact(value)}</span></div>`;
    },
    _tooltipTotal(value) {
      return `<div style="display:flex;justify-content:space-between;gap:16px;font-size:12px;line-height:1.6;margin-top:4px;padding-top:4px;border-top:1px solid rgba(255,255,255,0.15)"><span style="color:rgba(255,255,255,0.7);text-transform:uppercase;letter-spacing:0.06em;font-size:10px">Total</span><span style="font-family:'Cascadia Mono',Consolas,ui-monospace,monospace;font-weight:700">${this.fmtExact(value)}</span></div>`;
    },
    _axisTooltipFormatter(title) {
      return (params) => {
        if (!params?.length) return "";
        const header = title ? title(params[0]) : params[0].axisValueLabel;
        let total = 0;
        const rows = params.map((p) => {
          const v = Array.isArray(p.value) ? p.value[1] : p.value;
          total += Number(v) || 0;
          return this._tooltipRow(p.color, p.seriesName, v);
        }).join("");
        const head = `<div style="font-size:11px;color:rgba(255,255,255,0.7);margin-bottom:6px">${header}</div>`;
        return head + rows + (params.length > 1 ? this._tooltipTotal(total) : "");
      };
    },
    fmtPct(x) {
      if (x == null) return "—";
      return (x * 100).toFixed(1) + "%";
    },
    fmtUsd(x) {
      if (x == null) return "—";
      return "$" + x.toFixed(2);
    },
    fmtReuse(x) {
      if (x == null || x === 0) return "no cache writes yet";
      return x.toFixed(1) + "× avg reuse per cached token";
    },
    fmtTrend(pct) {
      if (pct == null) return "—";
      if (pct === 0) return "flat vs last week";
      const arrow = pct > 0 ? "↑" : "↓";
      return arrow + " " + (Math.abs(pct) * 100).toFixed(1) + "% vs last week";
    },
    fmtHour(h) {
      if (h == null) return "—";
      const hr12 = ((h + 11) % 12) + 1;
      const next12 = ((h + 1 + 11) % 12) + 1;
      const nextAmPm = (h + 1) % 24 < 12 ? "AM" : "PM";
      return `${hr12} – ${next12} ${nextAmPm}`;
    },
    fmtActive(tpm) {
      if (tpm == null) return "Idle";
      return this.fmt(Math.round(tpm)) + " tok / min";
    },
    fmtWhen(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now - d;
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return mins + "m ago";
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return hrs + "h ago";
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    },

    dailyChartTitle() {
      const labels = { "24h": "Last 24 hours", "7d": "7-day token usage", "30d": "30-day token usage", "all": "All-time token usage" };
      return labels[this.range] || "Token usage";
    },
    dailyChartSub() {
      if (this.range === "24h") return "Stacked by type (hourly bucketing; moving average not applicable)";
      return "Stacked by type · 7-day moving average overlay";
    },

    sparkSeries(which) {
      const daily = this.data.daily || {};
      const days = Object.keys(daily).slice(-12);
      return days.map((d) => {
        const row = daily[d];
        if (which === "total") return row.total;
        if (which === "today") return row.total;
        if (which === "efficiency") {
          const denom = row.input + row.cache_read + row.cache_create;
          return denom > 0 ? row.cache_read / denom : 0;
        }
        if (which === "savings") return row.cache_read;
        return 0;
      });
    },

    sparkBars(values, _cls) {
      if (!values || values.length === 0) {
        return Array(8).fill('<span style="height:5%" data-tip="No activity"></span>').join("");
      }
      const max = Math.max(...values, 1);
      return values
        .map((v) => {
          const tip = `${this.fmtExact(v)} tokens`;
          return `<span style="height:${Math.max(5, (v / max) * 100)}%" data-tip="${tip}"></span>`;
        })
        .join("");
    },
    sparkBarsHero(which) {
      const daily = this.data.daily || {};
      const days = Object.keys(daily).slice(-12);
      if (days.length === 0) {
        return Array(8).fill('<span style="height:5%" data-tip="No data"></span>').join("");
      }
      const raw = days.map((d) => {
        const row = daily[d];
        if (which === "efficiency") {
          const denom = row.input + row.cache_read + row.cache_create;
          return denom > 0 ? row.cache_read / denom : 0;
        }
        if (which === "savings") return row.cache_read;
        return row.total;
      });
      const max = Math.max(...raw, which === "efficiency" ? 0.01 : 1);
      const fmtTip = (v, dateStr) => {
        const label = dateStr.length >= 10 ? dateStr.slice(5) : dateStr;
        if (which === "efficiency") return `${label} · ${(v * 100).toFixed(1)}% from cache`;
        if (which === "savings") return `${label} · ${this.fmtExact(v)} cache-read tokens`;
        return `${label} · ${this.fmtExact(v)} tokens`;
      };
      return raw.map((v, i) => {
        const tip = fmtTip(v, days[i]);
        return `<span style="height:${Math.max(5, (v / max) * 100)}%" data-tip="${tip}"></span>`;
      }).join("");
    },

    _initCharts() {
      this.charts.daily = echarts.init(document.getElementById("chart-daily"));
      this.charts.heatmap = echarts.init(document.getElementById("chart-heatmap"));
      this.charts.donut = echarts.init(document.getElementById("chart-donut"));
      this.charts.projects = echarts.init(document.getElementById("chart-projects"));
      this.charts.models = echarts.init(document.getElementById("chart-models"));
    },

    _resizeCharts() {
      Object.values(this.charts).forEach((c) => c && c.resize());
    },

    _renderCharts() {
      this._renderDaily();
      this._renderHeatmap();
      this._renderDonut();
      this._renderProjects();
      this._renderModels();
    },

    _renderDaily() {
      const daily = this.data.daily || {};
      const dates = Object.keys(daily);
      const axis = dates.map((d) => d.slice(5));
      const input = dates.map((d) => daily[d].input);
      const output = dates.map((d) => daily[d].output);
      const cacheW = dates.map((d) => daily[d].cache_create);
      const cacheR = dates.map((d) => daily[d].cache_read);
      const totals = dates.map((d) => daily[d].total);
      const avg = totals.map((_, i) => {
        const win = totals.slice(Math.max(0, i - 6), i + 1);
        return win.reduce((a, b) => a + b, 0) / win.length;
      });

      const mkSeries = (name, data, color) => ({
        name,
        type: "line",
        stack: "tokens",
        smooth: true,
        showSymbol: false,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: color + "e6" },
            { offset: 1, color: color + "0d" },
          ]),
        },
        lineStyle: { width: 0 },
        data,
      });

      this.charts.daily.setOption(
        {
          animationDuration: 600,
          grid: { left: 40, right: 16, top: 20, bottom: 30 },
          tooltip: { show: false },
          legend: { show: false },
          xAxis: { type: "category", data: axis, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10 } },
          yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(255,255,255,0.07)" } }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          series: [
            mkSeries("Input",       input,  "#60a5fa"),
            mkSeries("Output",      output, "#ec4899"),
            mkSeries("Cache write", cacheW, "#fbbf24"),
            mkSeries("Cache read",  cacheR, "#34d399"),
            {
              name: "7-day avg",
              type: "line",
              smooth: true,
              showSymbol: false,
              lineStyle: { color: "#ffffff", width: 2, type: "dashed" },
              data: avg,
            },
          ],
        },
        { notMerge: false },
      );
    },

    _renderHeatmap() {
      const cells = this.data.heatmap || [];
      const maxVal = cells.reduce((m, c) => Math.max(m, c[2]), 0) || 1;
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      this.charts.heatmap.setOption(
        {
          tooltip: {
            formatter: (p) => {
              const hour = p.data[0];
              const day = days[p.data[1]];
              const hh = String(hour).padStart(2, "0");
              return `${day} ${hh}:00 — ${this.fmtExact(p.data[2])} tokens`;
            },
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
            confine: true,
            extraCssText: "max-width: 260px; white-space: normal; box-shadow: 0 8px 24px rgba(0,0,0,0.45);",
          },
          grid: { left: 40, right: 16, top: 16, bottom: 30 },
          xAxis: { type: "category", data: Array.from({ length: 24 }, (_, i) => i), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 9, interval: 2 } },
          yAxis: { type: "category", data: days, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10 } },
          visualMap: {
            min: 0, max: maxVal, show: false,
            inRange: { color: ["rgba(139,92,246,0.08)", "#8b5cf6", "#ec4899"] },
          },
          series: [{ type: "heatmap", data: cells, itemStyle: { borderRadius: 3 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(236,72,153,0.6)" } } }],
        },
        { notMerge: false },
      );
    },

    _renderDonut() {
      const m = this.data.token_mix || { input: 0, output: 0, cache_create: 0, cache_read: 0 };
      this.charts.donut.setOption(
        {
          tooltip: {
            trigger: "item",
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
            confine: true,
            extraCssText: "max-width: 260px; white-space: normal; box-shadow: 0 8px 24px rgba(0,0,0,0.45);",
            formatter: (p) => {
              const pct = (p.percent ?? 0).toFixed(1) + "%";
              const head = `<div style="font-size:11px;color:rgba(255,255,255,0.7);margin-bottom:6px">${p.name} · ${pct}</div>`;
              return head + this._tooltipRow(p.color, "Tokens", p.value);
            },
          },
          legend: { bottom: 0, textStyle: { color: "rgba(255,255,255,0.75)", fontSize: 11 }, itemWidth: 10, itemHeight: 10, icon: "roundRect" },
          series: [{
            type: "pie",
            radius: ["55%", "80%"],
            center: ["50%", "45%"],
            label: { show: false },
            labelLine: { show: false },
            data: [
              { value: m.input, name: "Input", itemStyle: { color: "#60a5fa" } },
              { value: m.output, name: "Output", itemStyle: { color: "#ec4899" } },
              { value: m.cache_create, name: "Cache W", itemStyle: { color: "#fbbf24" } },
              { value: m.cache_read, name: "Cache R", itemStyle: { color: "#34d399" } },
            ],
          }],
        },
        { notMerge: false },
      );
    },

    _renderProjects() {
      const by = this.data.by_project || {};
      const names = Object.keys(by).slice(0, 6).reverse();
      const input = names.map((n) => by[n].input);
      const output = names.map((n) => by[n].output);
      const cw = names.map((n) => by[n].cache_create);
      const cr = names.map((n) => by[n].cache_read);
      const mkBar = (name, data, color) => ({
        name, type: "bar", stack: "t", data,
        itemStyle: { color, borderRadius: [0, 0, 0, 0] },
      });
      this.charts.projects.setOption(
        {
          tooltip: {
            trigger: "item",
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
            confine: true,
            extraCssText: "max-width: 260px; white-space: normal; box-shadow: 0 8px 24px rgba(0,0,0,0.45);",
            formatter: (p) => {
              const proj = p.name;
              const row = by[proj] || {};
              const total = (row.input || 0) + (row.output || 0) + (row.cache_create || 0) + (row.cache_read || 0);
              const head = `<div style="font-size:11px;color:rgba(255,255,255,0.7);margin-bottom:6px">${proj}</div>`;
              return head
                + this._tooltipRow("#60a5fa", "Input", row.input || 0)
                + this._tooltipRow("#ec4899", "Output", row.output || 0)
                + this._tooltipRow("#fbbf24", "Cache W", row.cache_create || 0)
                + this._tooltipRow("#34d399", "Cache R", row.cache_read || 0)
                + this._tooltipTotal(total);
            },
          },
          grid: { left: 110, right: 30, top: 8, bottom: 20 },
          xAxis: { type: "value", splitLine: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          yAxis: { type: "category", data: names, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11 } },
          series: [
            mkBar("Input", input, "#60a5fa"),
            mkBar("Output", output, "#ec4899"),
            mkBar("Cache W", cw, "#fbbf24"),
            mkBar("Cache R", cr, "#34d399"),
          ],
        },
        { notMerge: false },
      );
    },

    _renderModels() {
      const by = this.data.by_model || {};
      const names = Object.keys(by).slice(0, 6).reverse();
      const totals = names.map((n) => by[n].total);
      const colors = ["#8b5cf6", "#06b6d4", "#34d399", "#ec4899", "#fbbf24", "#f97316"];
      this.charts.models.setOption(
        {
          tooltip: {
            trigger: "item",
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
            confine: true,
            extraCssText: "max-width: 260px; white-space: normal; box-shadow: 0 8px 24px rgba(0,0,0,0.45);",
            formatter: (p) => {
              const model = p.name;
              const row = by[model] || {};
              const total = row.total || p.value || 0;
              const head = `<div style="font-size:11px;color:rgba(255,255,255,0.7);margin-bottom:6px">${model}</div>`;
              return head
                + this._tooltipRow("#60a5fa", "Input", row.input || 0)
                + this._tooltipRow("#ec4899", "Output", row.output || 0)
                + this._tooltipRow("#fbbf24", "Cache W", row.cache_create || 0)
                + this._tooltipRow("#34d399", "Cache R", row.cache_read || 0)
                + this._tooltipTotal(total);
            },
          },
          grid: { left: 90, right: 40, top: 8, bottom: 20 },
          xAxis: { type: "value", splitLine: { show: false }, axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 10, formatter: (v) => this.fmt(v) } },
          yAxis: { type: "category", data: names, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11, fontFamily: "Cascadia Mono, Consolas, ui-monospace, monospace" } },
          series: [{
            type: "bar",
            data: totals.map((v, i) => ({ value: v, itemStyle: { color: colors[i % colors.length], borderRadius: 999 } })),
          }],
        },
        { notMerge: false },
      );
    },
  };
}

document.addEventListener("alpine:init", () => {
  Alpine.data("dashboard", dashboard);
});
