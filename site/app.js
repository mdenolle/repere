/* FrugalMind EvalHub — cost-vs-performance chart with skill-lift lines.
 *
 * Each model contributes two points per eval: without the domain skill (hollow)
 * and with it (filled), joined by a line. The line IS the skill lift. Up is
 * better, left is cheaper, so the best systems sit upper-left.
 *
 * No chart library: a hand-rolled SVG so the page stays dependency-free and the
 * PNG export is exact.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/* Eval categories. Keep in sync with the `category` field the exporter writes;
 * this map is the fallback for older data files that predate it. */
const SUITE_CATEGORY = {
  synthetic_stalta: "software-agent",
  dvv_processing: "software-agent",
  lit_rag: "document",
  orchestration: "research-workflow",
};

const CATEGORIES = {
  document: { label: "Document-based", color: "var(--c1)", hex: "#4b2e83" },
  "software-agent": { label: "Software-agent", color: "var(--c2)", hex: "#1b7f79" },
  "research-workflow": { label: "Research-workflow", color: "var(--c3)", hex: "#c2571a" },
};

/* Per-model palette + static metadata for the hover card. */
const MODEL_META = {
  "qwen2.5:7b": { size_b: 7, hex: "#4b2e83", params: "7B", license: "Apache-2.0", org: "Alibaba" },
  "llama3.1:8b": { size_b: 8, hex: "#1b7f79", params: "8B", license: "Llama 3", org: "Meta" },
  "deepseek-r1:7b": { size_b: 7, hex: "#c2571a", params: "7B", license: "MIT", org: "DeepSeek" },
  "olmo2:7b": { size_b: 7, hex: "#2f6fb2", params: "7B", license: "Apache-2.0", org: "AI2" },
  "claude-haiku-4-5-20251001": { hex: "#8a1f5e", params: "n/d", license: "proprietary", org: "Anthropic" },
};
const FALLBACK_HEX = "#6f6890";

const OPENNESS_LABEL = {
  "open-source-open-weight": "open weights",
  "open-source-closed-weight": "open code, closed weights",
  "closed-source-api": "closed — API only",
  "closed-source-ui": "closed — UI only",
  unknown: "unknown",
};

// Each eval gets its own MARKER SHAPE, so the two tasks are distinguishable
// when both are plotted together (colour already encodes the model).
const SUITE_SHAPE = {
  dvv_processing: "circle",   // E2 · parameter selection
  synthetic_stalta: "square", // E1 · code generation
};
const SUITE_LABEL = {
  dvv_processing: "dv/v processing (parameter selection)",
  synthetic_stalta: "STA/LTA detection (code generation)",
};

// Selectable x-axis. Cost alone flatters local models: they bill $0 but are far
// slower, and that wall-clock latency is a real cost a laboratory pays. Model
// size reframes skill lift as "how many parameters is this skill worth?".
const X_AXES = {
  cost: {
    label: "Cost per run (USD) — local open-weight models bill $0",
    short: "Cost per run (USD)",
    none: (r) => r.cost_none_usd,
    full: (r) => r.cost_full_usd,
    fmt: (v) => (v === 0 ? "$0" : `$${v.toFixed(3)}`),
  },
  latency: {
    label: "Wall-clock latency per run (s) — the cost a $0 model still charges",
    short: "Latency per run (s)",
    none: (r) => r.latency_none_s,
    full: (r) => r.latency_full_s,
    fmt: (v) => `${Math.round(v)}s`,
  },
  size: {
    // Static property of the model, so it needs no measurement and works even on
    // result files produced before the run recorded `size_b`.
    label: "Model size (billion parameters) — how many parameters is the skill worth?",
    short: "Model size (B params)",
    none: (r) => r.size_b ?? (MODEL_META[r.model_id] || {}).size_b,
    full: (r) => r.size_b ?? (MODEL_META[r.model_id] || {}).size_b,
    fmt: (v) => `${v}B`,
  },
};

const state = { rows: [], category: "all", xaxis: "cost", meta: {} };

/* ------------------------------------------------------------------ utils */
const fmtCost = (v) => (v === 0 ? "$0 (local)" : `$${Number(v).toFixed(4)}`);
const fmtPct = (v) => `${(Number(v) * 100).toFixed(0)}%`;
const modelHex = (id) => (MODEL_META[id] || {}).hex || FALLBACK_HEX;

function categoryOf(row) {
  return row.category || SUITE_CATEGORY[row.suite] || "software-agent";
}

async function loadJson(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ------------------------------------------------------------------- chart */
/* Responsive geometry.
 *
 * The SVG scales to its container, so a 900-unit viewBox on a ~355px phone is
 * drawn at 0.4x — an 11px label renders at ~4px and a 6px marker at ~2.5px:
 * illegible and untappable. Compensating with CSS alone does not work, because
 * the whole coordinate system shrinks.
 *
 * So on narrow screens we use a NARROWER viewBox (less downscaling) and larger
 * type and markers in user units, which survive the scale. */
function layout() {
  const w = typeof window !== "undefined" ? window.innerWidth : 1200;
  const narrow = w < 700;
  if (narrow) {
    return {
      W: 420, H: 460,
      M: { top: 20, right: 14, bottom: 74, left: 46 },
      fAxis: 13, fLabel: 14, rHollow: 7, rFilled: 8, lw: 2.2, narrow: true,
    };
  }
  return {
    W: 900, H: 480,
    M: { top: 24, right: 26, bottom: 56, left: 62 },
    fAxis: 11, fLabel: 12, rHollow: 6, rFilled: 7, lw: 1.6, narrow: false,
  };
}

function marker(shape, cx, cy, r, attrs, parent) {
  if (shape === "square") {
    return el("rect", {
      ...attrs, x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, rx: 1.5,
    }, parent);
  }
  return el("circle", { ...attrs, cx, cy, r }, parent);
}

function el(name, attrs = {}, parent = null) {
  const n = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function draw() {
  const svg = document.querySelector("#chart");
  svg.innerHTML = "";

  const L = layout();
  const { W, H, M } = L;
  const PW = W - M.left - M.right;
  const PH = H - M.top - M.bottom;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  // `let`, not `const`: the x-axis filter below narrows this to the rows that
  // actually carry the selected metric. Reassigning a `const` here threw
  // "Assignment to constant variable" and killed the entire chart. A syntax
  // check does not catch that — only rendering does.
  let rows = state.rows.filter(
    (r) => state.category === "all" || categoryOf(r) === state.category
  );

  const note = document.querySelector("#chart-note");
  if (!rows.length) {
    note.textContent = "No evals in this category yet.";
    document.querySelector("#legend").innerHTML = "";
    return;
  }

  const ax = X_AXES[state.xaxis];
  // Rows produced before a metric existed simply have no value for it.
  const usable = rows.filter(
    (r) => Number.isFinite(ax.none(r)) && Number.isFinite(ax.full(r))
  );
  if (!usable.length) {
    note.textContent = `No data for the "${state.xaxis}" axis yet — re-run the eval to record it.`;
    document.querySelector("#legend").innerHTML = "";
    return;
  }
  rows = usable;
  const maxX = Math.max(...rows.flatMap((r) => [ax.none(r), ax.full(r)]), 1e-9);
  const xMax = maxX * 1.18;
  const x = (v) => M.left + (v / xMax) * PW;
  const y = (v) => M.top + (1 - v) * PH; // score is already 0..1

  // gridlines + y axis
  const g = el("g", {}, svg);
  for (let i = 0; i <= 5; i++) {
    const yv = i / 5;
    el("line", {
      class: "gridline", x1: M.left, x2: M.left + PW, y1: y(yv), y2: y(yv),
    }, g);
    el("text", {
      class: "axis", x: M.left - 8, y: y(yv) + 4, "text-anchor": "end",
      "font-size": L.fAxis,
    }, g).textContent = fmtPct(yv);
  }
  // x ticks
  const nTicks = L.narrow ? 2 : 4;   // 4 tick labels collide on a phone
  for (let i = 0; i <= nTicks; i++) {
    const xv = (xMax / nTicks) * i;
    el("text", {
      class: "axis", x: x(xv), y: M.top + PH + 20, "text-anchor": "middle",
      "font-size": L.fAxis,
    }, g).textContent = ax.fmt(xv);
  }
  el("line", { class: "axis", x1: M.left, x2: M.left + PW, y1: M.top + PH, y2: M.top + PH }, g);
  el("line", { class: "axis", x1: M.left, x2: M.left, y1: M.top, y2: M.top + PH }, g);

  el("text", {
    class: "axis-label", x: M.left + PW / 2, y: H - (L.narrow ? 44 : 14),
    "text-anchor": "middle", "font-size": L.fLabel,
  }, g).textContent = L.narrow ? (ax.short || ax.label) : ax.label;
  el("text", {
    class: "axis-label", transform: `rotate(-90)`, x: -(M.top + PH / 2),
    y: L.narrow ? 14 : 16, "text-anchor": "middle", "font-size": L.fLabel,
  }, g).textContent = L.narrow ? "Score" : "Performance (deterministic score)";

  // "better" hint
  el("text", {
    class: "axis", x: M.left + 4, y: M.top + 12, fill: "#6d5bd0",
    "font-size": L.fAxis,
  }, g).textContent = L.narrow ? "↖ better" : "↖ cheaper + better";

  // one lift-line + two markers per row
  for (const r of rows) {
    const hex = modelHex(r.model_id);
    const shape = SUITE_SHAPE[r.suite] || "circle";
    const x0 = x(ax.none(r)), y0 = y(r.score_none);
    const x1 = x(ax.full(r)), y1 = y(r.score_full);

    el("line", {
      class: "lift-line", x1: x0, y1: y0, x2: x1, y2: y1,
      stroke: hex, "stroke-width": L.lw, "marker-end": "url(#arrow)",
    }, g);

    // 95% CI over repeat runs, when the repeat study has been run.
    for (const [xv, yv, ci] of [[x0, r.score_none, r.score_none_ci95],
                                [x1, r.score_full, r.score_full_ci95]]) {
      if (ci > 0) {
        el("line", {
          class: "errbar", x1: xv, x2: xv, y1: y(Math.min(1, yv + ci)),
          y2: y(Math.max(0, yv - ci)), stroke: hex, "stroke-width": 1.2, opacity: 0.7,
        }, g);
      }
    }

    const hollow = marker(shape, x0, y0, L.rHollow,
      { class: "pt", fill: "#fff", stroke: hex, "stroke-width": 2 }, g);
    const filled = marker(shape, x1, y1, L.rFilled,
      { class: "pt", fill: hex, stroke: "#fff", "stroke-width": 1.5 }, g);

    bindTip(hollow, r, "none");
    bindTip(filled, r, "full");
  }

  // arrowhead
  const defs = el("defs", {}, svg);
  // NB: named `arrowMarker`, not `marker` — a local `const marker` here would
  // shadow the marker() helper above for the whole of draw() and throw a TDZ
  // ReferenceError on first use, silently killing the chart.
  const arrowMarker = el("marker", {
    id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
    markerWidth: 5, markerHeight: 5, orient: "auto-start-reverse",
  }, defs);
  el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#6f6890", opacity: 0.5 }, arrowMarker);

  note.textContent =
    `${rows.length} model×eval pairs. Hollow marker = no skill; filled = skill loaded; ` +
    `the line is the lift. ${state.meta.note || ""}`;

  renderLegend(rows);
  renderTable(rows);
}

function legendGroup(box, title) {
  const g = document.createElement("div");
  g.className = "legend-group";
  const h = document.createElement("span");
  h.className = "legend-title";
  h.textContent = title;
  g.appendChild(h);
  box.appendChild(g);
  return g;
}

/* The chart carries TWO independent encodings and the legend must say so
 * explicitly, or the reader has to reverse-engineer it:
 *   colour = base model      shape = task
 * Splitting them into labelled groups is the difference between a legend that
 * documents the chart and one that merely lists things. */
function renderLegend(rows) {
  const box = document.querySelector("#legend");
  box.innerHTML = "";

  // ---- 1. Base models (colour) ----
  const gModels = legendGroup(box, "Base model");
  for (const id of [...new Set(rows.map((r) => r.model_id))].sort()) {
    const meta = MODEL_META[id] || {};
    const item = document.createElement("span");
    item.className = "legend-item";
    const sw = document.createElement("span");
    sw.className = "legend-swatch";
    sw.style.background = modelHex(id);
    item.appendChild(sw);
    const label = meta.params && meta.params !== "n/d" ? `${id} (${meta.params})` : id;
    item.appendChild(document.createTextNode(label));
    gModels.appendChild(item);
  }

  // ---- 2. Tasks (shape) ----
  // Draw the ACTUAL marker shape, not a coloured dot: shape is the message here,
  // so a circle/square swatch is the only honest key.
  const gTasks = legendGroup(box, "Task");
  for (const suite of [...new Set(rows.map((r) => r.suite))].sort()) {
    const shape = SUITE_SHAPE[suite] || "circle";
    const item = document.createElement("span");
    item.className = "legend-item";

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", 14);
    svg.setAttribute("height", 14);
    svg.setAttribute("class", "legend-shape");
    marker(shape, 7, 7, 5, { fill: "#6f6890", stroke: "#fff", "stroke-width": 1 }, svg);
    item.appendChild(svg);

    item.appendChild(document.createTextNode(SUITE_LABEL[suite] || suite));
    gTasks.appendChild(item);
  }

  // ---- 3. Skill condition (fill) — needed to read the arrows at all ----
  const gSkill = legendGroup(box, "Skill");
  for (const [label, filled] of [["no skill", false], ["skill loaded", true]]) {
    const item = document.createElement("span");
    item.className = "legend-item";
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", 14);
    svg.setAttribute("height", 14);
    svg.setAttribute("class", "legend-shape");
    marker("circle", 7, 7, 5, filled
      ? { fill: "#6f6890", stroke: "#fff", "stroke-width": 1 }
      : { fill: "#fff", stroke: "#6f6890", "stroke-width": 1.8 }, svg);
    item.appendChild(svg);
    item.appendChild(document.createTextNode(label));
    gSkill.appendChild(item);
  }
}

function renderTable(rows) {
  const body = document.querySelector("#data-table-body");
  if (!body) return;
  body.innerHTML = "";
  const sorted = [...rows].sort(
    (a, b) => a.suite.localeCompare(b.suite) || b.lift - a.lift
  );
  for (const r of sorted) {
    const tr = document.createElement("tr");
    const cells = [
      r.model_id,
      SUITE_LABEL[r.suite] || r.suite,
      fmtPct(r.score_none),
      fmtPct(r.score_full),
      `${r.lift >= 0 ? "+" : ""}${(r.lift * 100).toFixed(0)} pp`,
      fmtCost(r.cost_full_usd),
    ];
    cells.forEach((c, i) => {
      const cell = document.createElement(i === 0 ? "th" : "td");
      if (i === 0) cell.setAttribute("scope", "row");
      cell.textContent = c;
      tr.appendChild(cell);
    });
    body.appendChild(tr);
  }
}

function renderAxisPicker() {
  const box = document.querySelector("#xaxis-picker");
  if (!box) return;
  box.innerHTML = "";
  const labels = { cost: "Cost ($)", latency: "Latency (s)", size: "Model size (B)" };
  for (const key of Object.keys(X_AXES)) {
    const ax = X_AXES[key];
    const has = state.rows.some(
      (r) => Number.isFinite(ax.none(r)) && Number.isFinite(ax.full(r))
    );
    const b = document.createElement("button");
    b.className = "chip";
    b.type = "button";
    b.textContent = labels[key] + (has ? "" : " — not yet measured");
    b.disabled = !has;
    b.setAttribute("aria-pressed", state.xaxis === key);
    b.addEventListener("click", () => {
      state.xaxis = key;
      renderAxisPicker();
      draw();
    });
    box.appendChild(b);
  }
}

/* ----------------------------------------------------------------- tooltip */
const tip = () => document.querySelector("#tooltip");

function bindTip(node, r, arm) {
  const m = MODEL_META[r.model_id] || {};
  const isFull = arm === "full";
  const score = isFull ? r.score_full : r.score_none;
  const cost = isFull ? r.cost_full_usd : r.cost_none_usd;
  const html = `
    <b>${r.model_id}</b><br/>
    <span class="kv">weights:</span> ${OPENNESS_LABEL[r.openness] || r.openness}
    ${m.params ? ` · ${m.params}` : ""}${m.license ? ` · ${m.license}` : ""}<br/>
    <span class="kv">eval:</span> ${r.suite} <span class="kv">(${CATEGORIES[categoryOf(r)].label})</span><br/>
    <span class="kv">skill:</span> ${isFull ? `${r.skill_name} ${r.skill_version}` : "none (baseline)"}<br/>
    <span class="kv">score:</span> <b>${fmtPct(score)}</b> · <span class="kv">cost:</span> ${fmtCost(cost)}<br/>
    <span class="kv">skill lift:</span> ${(r.lift * 100).toFixed(0)} pp
  `;

  function show(clientX, clientY) {
    const t = tip();
    t.innerHTML = html;
    t.style.opacity = 1;
    place(clientX, clientY);
  }
  function place(clientX, clientY) {
    const t = tip();
    const w = 300, pad = 10;
    // Keep the card on-screen. On a phone a naive x+14 pushes it off the right
    // edge and the text is unreadable.
    const vw = window.innerWidth, vh = window.innerHeight;
    let left = clientX + 14;
    if (left + w + pad > vw) left = Math.max(pad, clientX - w - 14);
    let top = clientY + 14;
    if (top + 160 > vh) top = Math.max(pad, clientY - 170);
    t.style.left = `${left}px`;
    t.style.top = `${top}px`;
  }
  const hide = () => (tip().style.opacity = 0);

  // Pointer (mouse) — hover.
  node.addEventListener("mouseenter", (e) => show(e.clientX, e.clientY));
  node.addEventListener("mousemove", (e) => place(e.clientX, e.clientY));
  node.addEventListener("mouseleave", hide);

  // TOUCH — there is no hover on a phone, so without this every marker's data is
  // simply unreachable on mobile. Tap shows the card; tapping elsewhere hides it.
  node.addEventListener("touchstart", (e) => {
    e.preventDefault();          // don't also fire a synthetic mouse event
    e.stopPropagation();
    const t = e.touches[0];
    show(t.clientX, t.clientY);
  }, { passive: false });
  node.addEventListener("click", (e) => {
    e.stopPropagation();
    show(e.clientX, e.clientY);
  });
}

// Dismiss the tooltip when tapping anywhere else.
if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("touchstart", () => {
    const t = document.querySelector("#tooltip");
    if (t) t.style.opacity = 0;
  });
}

/* ----------------------------------------------------------------- filters */
function renderFilters() {
  const box = document.querySelector("#filters");
  box.innerHTML = "";
  const present = new Set(state.rows.map(categoryOf));
  const opts = [["all", "All evals"], ...Object.entries(CATEGORIES).map(([k, v]) => [k, v.label])];
  for (const [key, label] of opts) {
    const b = document.createElement("button");
    b.className = "chip";
    b.type = "button";
    b.textContent = label + (key !== "all" && !present.has(key) ? " (soon)" : "");
    b.setAttribute("aria-pressed", state.category === key);
    if (key !== "all" && !present.has(key)) b.disabled = true;
    b.addEventListener("click", () => {
      state.category = key;
      renderFilters();
      draw();
    });
    box.appendChild(b);
  }
}

/* --------------------------------------------------------------- downloads */
function downloadBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportCsv() {
  const rows = state.rows.filter(
    (r) => state.category === "all" || categoryOf(r) === state.category
  );
  const cols = [
    "model_id", "category", "suite", "openness", "toolset",
    "skill_name", "skill_version",
    "score_none", "score_full", "lift",
    "cost_none_usd", "cost_full_usd", "n_total",
  ];
  const lines = [cols.join(",")];
  for (const r of rows) {
    lines.push(
      cols
        .map((c) => {
          const v = c === "category" ? categoryOf(r) : r[c];
          const s = v === null || v === undefined ? "" : String(v);
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        })
        .join(",")
    );
  }
  downloadBlob(new Blob([lines.join("\n")], { type: "text/csv" }), "frugalmind-leaderboard.csv");
}

/* Rasterise the SVG for publication. External CSS does not apply inside an
 * <img>, so inline the rules the chart depends on before serialising. */
const EXPORT_CSS = `
  .axis text { fill:#6f6890; font-size:11px; font-family:Inter,sans-serif; }
  .axis line, .axis path { stroke:rgba(42,26,79,0.10); }
  .axis-label { fill:#2a1a4f; font-size:12px; font-weight:600; font-family:Inter,sans-serif; }
  .gridline { stroke:rgba(42,26,79,0.06); }
  .lift-line { stroke-width:1.6; opacity:0.5; }
  text { font-family: Inter, system-ui, sans-serif; }
`;

function exportPng() {
  const src = document.querySelector("#chart");
  const clone = src.cloneNode(true);
  clone.setAttribute("xmlns", SVG_NS);
  clone.setAttribute("width", W);
  clone.setAttribute("height", H);
  const style = document.createElementNS(SVG_NS, "style");
  style.textContent = EXPORT_CSS;
  clone.insertBefore(style, clone.firstChild);
  const bg = document.createElementNS(SVG_NS, "rect");
  bg.setAttribute("width", W);
  bg.setAttribute("height", H);
  bg.setAttribute("fill", "#ffffff");
  clone.insertBefore(bg, clone.firstChild);

  const xml = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  img.onload = () => {
    const scale = 2; // 2x for print
    const canvas = document.createElement("canvas");
    canvas.width = W * scale;
    canvas.height = H * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    canvas.toBlob((b) => downloadBlob(b, "frugalmind-cost-vs-performance.png"), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

/* -------------------------------------------------------------------- main */
async function main() {
  try {
    const sl = await loadJson("data/skill_lift.json");
    state.rows = sl.rows || [];
    state.meta = { note: (sl.notes || [])[0] || "" };
    document.querySelector("#generated-at").textContent = sl.generated_at
      ? `Updated ${new Date(sl.generated_at).toLocaleString(undefined, { dateStyle: "medium" })}`
      : "";
    document.querySelector("#source-label").textContent = sl.source || "";
  } catch (err) {
    document.querySelector("#chart-note").textContent = `Could not load results: ${err.message}`;
    document.querySelector("#generated-at").textContent = "unavailable";
    return;
  }
  renderFilters();
  renderAxisPicker();
  draw();
  // On a phone the table is easier to read than a downscaled scatter, so open it.
  const det = document.querySelector("#data-table-details");
  if (det && typeof window !== "undefined" && window.innerWidth < 700) det.open = true;
  document.querySelector("#dl-csv").addEventListener("click", exportCsv);
  document.querySelector("#dl-png").addEventListener("click", exportPng);

  // Re-draw on resize/rotate: the phone and desktop layouts use different
  // viewBoxes, so a rotation must rebuild the chart, not just rescale it.
  let t;
  window.addEventListener("resize", () => {
    clearTimeout(t);
    t = setTimeout(draw, 150);
  });
}

main();
