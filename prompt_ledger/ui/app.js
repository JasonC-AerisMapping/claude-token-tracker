/* global Alpine, echarts, pywebview */

function dashboard() {
  return {
    range: "30d",
    data: {},
    updatedAt: "—",
    charts: { daily: null, heatmap: null, donut: null, projects: null, models: null },

    async init() {
      this._initCharts();
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
    fmtPct(x) {
      if (x == null) return "—";
      return (x * 100).toFixed(1) + "%";
    },
    fmtUsd(x) {
      if (x == null) return "—";
      return "$" + x.toFixed(2);
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

    sparkSeries(which) {
      const daily = this.data.daily || {};
      const days = Object.keys(daily).slice(-12);
      return days.map((d) => {
        const row = daily[d];
        if (which === "total") return row.total;
        if (which === "today") return row.output;
        if (which === "hit") {
          const denom = row.input + row.cache_read;
          return denom > 0 ? row.cache_read / denom : 0;
        }
        if (which === "savings") return row.cache_read;
        return 0;
      });
    },

    sparkBars(values, _cls) {
      if (!values || values.length === 0) {
        return Array(8).fill('<span style="height:5%"></span>').join("");
      }
      const max = Math.max(...values, 1);
      return values
        .map((v) => `<span style="height:${Math.max(5, (v / max) * 100)}%"></span>`)
        .join("");
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
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
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
            formatter: (p) => `${days[p.data[0]]} ${p.data[1]}:00 — ${this.fmt(p.data[2])}`,
            backgroundColor: "#1a0b2e",
            borderColor: "#8b5cf6",
            textStyle: { color: "#fff" },
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
          tooltip: { trigger: "item", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
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
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
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
          tooltip: { trigger: "axis", backgroundColor: "#1a0b2e", borderColor: "#8b5cf6", textStyle: { color: "#fff" } },
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
