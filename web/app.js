// Crude Outlook front end.
// Loads data/forecast.json (written by crudeoil_prod/app.py) and draws the page.
// No frameworks or build step: plain JavaScript and hand-drawn SVG charts.

// Trading days of history shown before the forecast (fewer on phones so the forecast stays readable)
const historyDays = () => (window.innerWidth < 600 ? 60 : 120);

let DATA = null;
let asset = "wti";

const $ = (sel, root = document) => root.querySelector(sel);
const money = (v) => `$${v.toFixed(2)}`;
const pct = (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
const dir = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const fmtDate = (iso, opts = { month: "short", day: "numeric" }) =>
  new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", ...opts });

// ---------- Loading ----------
async function load() {
  try {
    const res = await fetch("data/forecast.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    DATA = await res.json();
  } catch (err) {
    const box = $("#load-error");
    box.hidden = false;
    box.textContent = `Couldn't load data/forecast.json (${err.message}). Run "python crudeoil_prod/app.py" to create it, then serve the web/ folder.`;
    return;
  }
  try { asset = localStorage.getItem("asset") || asset; } catch {}
  if (!DATA.assets[asset]) asset = "wti";
  render();
}

// ---------- Page text ----------
function setField(name, value) {
  document.querySelectorAll(`[data-field="${name}"]`).forEach((el) => (el.innerHTML = value));
}

function render() {
  const a = DATA.assets[asset];
  document.body.dataset.asset = asset;
  document.querySelectorAll("[data-pick]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pick === asset)));

  const dayChange = ((a.last_price - a.prev_price) / a.prev_price) * 100;
  const h7 = a.forecast[a.forecast.length - 1];
  const m1 = a.metrics["1"];

  setField("name", a.name);
  setField("description", a.description);
  setField("last_date", fmtDate(a.last_date));
  setField("last_price", money(a.last_price));
  setField("day_change", `<span class="${dir(dayChange)}">${pct(dayChange)}</span> from previous close`);
  setField("h7_date", fmtDate(h7.date, { weekday: "short", month: "short", day: "numeric" }));
  setField("h7_price", money(h7.price));
  setField("h7_range", `<span class="${dir(h7.change_pct)}">${pct(h7.change_pct)}</span> · likely ${money(h7.low)}–${money(h7.high)}`);
  setField("test_days", m1.test_days);
  setField("test_start", fmtDate(m1.test_start, { month: "long", day: "numeric", year: "numeric" }));
  setField("generated_at", new Date(DATA.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }));

  $("#days-body").innerHTML = a.forecast
    .map((f) => `<tr>
        <td>+${f.horizon}</td>
        <td class="date">${fmtDate(f.date, { weekday: "short", month: "short", day: "numeric" })}</td>
        <td class="num price">${money(f.price)}</td>
        <td class="num range">${money(f.low)} – ${money(f.high)}</td>
        <td class="num ${dir(f.change_pct)}">${pct(f.change_pct)}</td>
      </tr>`)
    .join("");

  document.querySelectorAll(".score").forEach((card) => renderScore(card, a.metrics[card.dataset.horizon], card.dataset.horizon));
  drawForecastChart(a);
  drawBacktestChart(a);
}

// Plain-language verdict: compare the model's average miss with the "no change" guess.
function renderScore(card, m, h) {
  const ratio = m.model_mae / m.naive_mae;
  const diff = Math.abs(1 - ratio) * 100;
  let verdict;
  if (diff < 2) verdict = "About as accurate as guessing “no change”.";
  else if (ratio < 1) verdict = `Misses by ${diff.toFixed(0)}% less than guessing “no change”.`;
  else verdict = `Misses by ${diff.toFixed(0)}% more than guessing “no change”.`;

  const max = Math.max(m.model_mae, m.naive_mae);
  const bar = (cls, label, v) => `<div class="bar-row ${cls}">
      <span>${label}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(v / max) * 100}%"></span></span>
      <span class="val">${money(v)}</span></div>`;

  card.innerHTML = `
    <h3>${h === "1" ? "Next trading day" : `${h} trading days ahead`}</h3>
    <p class="verdict">${verdict}</p>
    <div class="bars" aria-label="Average miss in dollars per barrel">
      ${bar("model", "Model", m.model_mae)}
      ${bar("naive", "“No change”", m.naive_mae)}
    </div>
    <p class="fine">Average miss, USD per barrel. It called the direction (up or down) right on
      <strong>${m.direction_accuracy.toFixed(0)}%</strong> of days; always guessing “up” would have scored
      ${m.always_up_accuracy.toFixed(0)}%.</p>`;
}

// ---------- SVG chart helpers ----------
const SVG_NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function makeFrame(container) {
  container.innerHTML = "";
  const w = container.clientWidth;
  const h = container.clientHeight;
  const pad = { top: 12, right: 54, bottom: 26, left: 8 };
  const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none" }, container);
  return { svg, w, h, pad, iw: w - pad.left - pad.right, ih: h - pad.top - pad.bottom };
}

function niceTicks(min, max, count = 5) {
  const step0 = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= step0 * 0.7);
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(v);
  return ticks;
}

function drawYAxis(f, y, ticks) {
  for (const t of ticks) {
    el("line", { class: "grid", x1: f.pad.left, x2: f.pad.left + f.iw, y1: y(t), y2: y(t) }, f.svg);
    const label = el("text", { class: "axis-text", x: f.w - 4, y: y(t) + 4, "text-anchor": "end" }, f.svg);
    label.textContent = `$${t}`;
  }
}

function drawMonthLabels(f, dates, x) {
  let lastMonth = null;
  const minGap = 48;
  let lastX = -Infinity;
  dates.forEach((d, i) => {
    const month = d.slice(0, 7);
    if (month !== lastMonth && x(i) - lastX > minGap) {
      const t = el("text", { class: "axis-text", x: x(i), y: f.h - 6 }, f.svg);
      t.textContent = fmtDate(d, { month: "short" });
      lastX = x(i);
    }
    lastMonth = month;
  });
}

const linePath = (pts) => pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");

// Hover readout: a vertical line and a small label following the pointer.
function addHover(f, n, x, describe) {
  const g = el("g", { visibility: "hidden" }, f.svg);
  const line = el("line", { class: "hover-line", y1: f.pad.top, y2: f.pad.top + f.ih }, g);
  const bg = el("rect", { class: "tip-bg", rx: 3, height: 22 }, g);
  const text = el("text", { class: "tip-text", y: f.pad.top + 15 }, g);
  const hit = el("rect", { x: f.pad.left, y: 0, width: f.iw, height: f.h, fill: "transparent" }, f.svg);
  const move = (evt) => {
    const box = f.svg.getBoundingClientRect();
    const px = ((evt.clientX - box.left) / box.width) * f.w;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - f.pad.left) / f.iw) * (n - 1))));
    const xi = x(i);
    line.setAttribute("x1", xi); line.setAttribute("x2", xi);
    text.textContent = describe(i);
    const tw = text.getComputedTextLength() + 14;
    const left = xi + tw + 8 > f.pad.left + f.iw ? xi - tw - 6 : xi + 6;
    bg.setAttribute("x", left); bg.setAttribute("y", f.pad.top); bg.setAttribute("width", tw);
    text.setAttribute("x", left + 7);
    g.setAttribute("visibility", "visible");
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", () => g.setAttribute("visibility", "hidden"));
}

// ---------- Main chart: history flowing into the forecast ----------
function drawForecastChart(a) {
  const f = makeFrame($("#chart"));
  const hist = a.history.slice(-historyDays());
  const fc = a.forecast;
  const n = hist.length + fc.length;
  const todayIdx = hist.length - 1;

  const values = [...hist.map((p) => p.price), ...fc.flatMap((p) => [p.low, p.high])];
  const lo = Math.min(...values), hi = Math.max(...values);
  const padY = (hi - lo) * 0.08;
  const ticks = niceTicks(lo - padY, hi + padY);
  const yMin = Math.min(lo - padY, ticks[0]), yMax = Math.max(hi + padY, ticks[ticks.length - 1]);
  const x = (i) => f.pad.left + (i / (n - 1)) * f.iw;
  const y = (v) => f.pad.top + (1 - (v - yMin) / (yMax - yMin)) * f.ih;

  // Hatched "future" zone: the part of the chart nobody has seen yet
  const defs = el("defs", {}, f.svg);
  const pattern = el("pattern", { id: "hatch", width: 7, height: 7, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  el("line", { class: "hatch-line", x1: 0, y1: 0, x2: 0, y2: 7 }, pattern);
  el("rect", { class: "future-zone", x: x(todayIdx), y: f.pad.top, width: x(n - 1) - x(todayIdx), height: f.ih }, f.svg);

  drawYAxis(f, y, ticks);
  drawMonthLabels(f, hist.map((p) => p.date), x);

  if (x(n - 1) - x(todayIdx) > 90) {
    const zoneLabel = el("text", { class: "zone-label", x: x(todayIdx) + 6, y: f.pad.top + f.ih - 8 }, f.svg);
    zoneLabel.textContent = "NEXT 7 DAYS";
  }
  el("line", { class: "today-line", x1: x(todayIdx), x2: x(todayIdx), y1: f.pad.top, y2: f.pad.top + f.ih }, f.svg);

  // Likely-range fan, starting as a point at today's close
  const today = hist[todayIdx].price;
  const upper = [[x(todayIdx), y(today)], ...fc.map((p, i) => [x(todayIdx + i + 1), y(p.high)])];
  const lower = [[x(todayIdx), y(today)], ...fc.map((p, i) => [x(todayIdx + i + 1), y(p.low)])].reverse();
  el("path", { class: "band", d: linePath(upper) + linePath(lower).replace("M", "L") + "Z" }, f.svg);

  el("path", { class: "history", d: linePath(hist.map((p, i) => [x(i), y(p.price)])) }, f.svg);
  el("path", { class: "forecast", d: linePath([[x(todayIdx), y(today)], ...fc.map((p, i) => [x(todayIdx + i + 1), y(p.price)])]) }, f.svg);
  el("circle", { class: "dot", cx: x(todayIdx), cy: y(today), r: 4.5 }, f.svg);
  el("circle", { class: "dot", cx: x(n - 1), cy: y(fc[fc.length - 1].price), r: 4.5 }, f.svg);

  addHover(f, n, x, (i) => {
    if (i <= todayIdx) return `${fmtDate(hist[i].date)}  ${money(hist[i].price)}`;
    const p = fc[i - todayIdx - 1];
    return `${fmtDate(p.date)}  ${money(p.price)} (${money(p.low)}–${money(p.high)})`;
  });
}

// ---------- Backtest chart: yesterday's forecast vs. what happened ----------
function drawBacktestChart(a) {
  const f = makeFrame($("#backtest"));
  const bt = a.backtest;
  if (!bt.length) return;
  const n = bt.length;
  const values = bt.flatMap((p) => [p.actual, p.predicted]);
  const lo = Math.min(...values), hi = Math.max(...values);
  const ticks = niceTicks(lo, hi, 4);
  const yMin = Math.min(lo, ticks[0]), yMax = Math.max(hi, ticks[ticks.length - 1]);
  const x = (i) => f.pad.left + (i / (n - 1)) * f.iw;
  const y = (v) => f.pad.top + (1 - (v - yMin) / (yMax - yMin)) * f.ih;

  drawYAxis(f, y, ticks);
  drawMonthLabels(f, bt.map((p) => p.date), x);
  el("path", { class: "history", d: linePath(bt.map((p, i) => [x(i), y(p.actual)])) }, f.svg);
  el("path", { class: "backtest-pred", d: linePath(bt.map((p, i) => [x(i), y(p.predicted)])) }, f.svg);
  addHover(f, n, x, (i) => `${fmtDate(bt[i].date)}  actual ${money(bt[i].actual)} · predicted ${money(bt[i].predicted)}`);
}

// ---------- Events ----------
document.querySelectorAll("[data-pick]").forEach((btn) =>
  btn.addEventListener("click", () => {
    asset = btn.dataset.pick;
    try { localStorage.setItem("asset", asset); } catch {}
    render();
  })
);

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => DATA && render(), 150);
});

load();
