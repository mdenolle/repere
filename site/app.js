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
  "qwen2.5:7b": { hex: "#4b2e83", params: "7B", license: "Apache-2.0", org: "Alibaba" },
  "llama3.1:8b": { hex: "#1b7f79", params: "8B", license: "Llama 3", org: "Meta" },
  "deepseek-r1:7b": { hex: "#c2571a", params: "7B", license: "MIT", org: "DeepSeek" },
  "olmo2:7b": { hex: "#2f6fb2", params: "7B", license: "Apache-2.0", org: "AI2" },
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

const state = { rows: [], category: "all", meta: {} };

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
const W = 900, H = 480;
const M = { top: 24, right: 26, bottom: 56, left: 62 };
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;

function el(name, attrs = {}, parent = null) {
  const n = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function draw() {
  const svg = document.querySelector("#chart");
  svg.innerHTML = "";

  const rows = state.rows.filter(
    (r) => state.category === "all" || categoryOf(r) === state.category
  );

  const note = document.querySelector("#chart-note");
  if (!rows.length) {
    note.textContent = "No evals in this category yet.";
    document.querySelector("#legend").innerHTML = "";
    return;
  }

  // x: cost. Local models are exactly $0, which is the point — keep 0 on-axis.
  const maxCost = Math.max(...rows.flatMap((r) => [r.cost_none_usd, r.cost_full_usd]), 0.01);
  const xMax = maxCost * 1.18;
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
      class: "axis", x: M.left - 10, y: y(yv) + 4, "text-anchor": "end",
    }, g).textContent = fmtPct(yv);
  }
  // x ticks
  for (let i = 0; i <= 4; i++) {
    const xv = (xMax / 4) * i;
    el("text", {
      class: "axis", x: x(xv), y: M.top + PH + 20, "text-anchor": "middle",
    }, g).textContent = i === 0 ? "$0" : `$${xv.toFixed(3)}`;
  }
  el("line", { class: "axis", x1: M.left, x2: M.left + PW, y1: M.top + PH, y2: M.top + PH }, g);
  el("line", { class: "axis", x1: M.left, x2: M.left, y1: M.top, y2: M.top + PH }, g);

  el("text", {
    class: "axis-label", x: M.left + PW / 2, y: H - 14, "text-anchor": "middle",
  }, g).textContent = "Cost per eval run (USD) — local open-weight models bill $0";
  el("text", {
    class: "axis-label", transform: `rotate(-90)`, x: -(M.top + PH / 2), y: 16,
    "text-anchor": "middle",
  }, g).textContent = "Performance (deterministic score)";

  // "better" hint
  el("text", {
    class: "axis", x: M.left + 6, y: M.top + 14, fill: "#6d5bd0",
  }, g).textContent = "↖ cheaper + better";

  // one lift-line + two markers per row
  for (const r of rows) {
    const hex = modelHex(r.model_id);
    const x0 = x(r.cost_none_usd), y0 = y(r.score_none);
    const x1 = x(r.cost_full_usd), y1 = y(r.score_full);

    el("line", {
      class: "lift-line", x1: x0, y1: y0, x2: x1, y2: y1,
      stroke: hex, "marker-end": "url(#arrow)",
    }, g);

    const hollow = el("circle", {
      class: "pt", cx: x0, cy: y0, r: 6, fill: "#fff", stroke: hex, "stroke-width": 2,
    }, g);
    const filled = el("circle", {
      class: "pt", cx: x1, cy: y1, r: 7, fill: hex, stroke: "#fff", "stroke-width": 1.5,
    }, g);

    bindTip(hollow, r, "none");
    bindTip(filled, r, "full");
  }

  // arrowhead
  const defs = el("defs", {}, svg);
  const marker = el("marker", {
    id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
    markerWidth: 5, markerHeight: 5, orient: "auto-start-reverse",
  }, defs);
  el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#6f6890", opacity: 0.5 }, marker);

  note.textContent =
    `${rows.length} model×eval pairs. Hollow marker = no skill; filled = skill loaded; ` +
    `the line is the lift. ${state.meta.note || ""}`;

  renderLegend(rows);
}

function renderLegend(rows) {
  const seen = [...new Set(rows.map((r) => r.model_id))];
  const box = document.querySelector("#legend");
  box.innerHTML = "";
  for (const id of seen) {
    const item = document.createElement("span");
    item.className = "legend-item";
    const sw = document.createElement("span");
    sw.className = "legend-swatch";
    sw.style.background = modelHex(id);
    item.appendChild(sw);
    item.appendChild(document.createTextNode(id));
    box.appendChild(item);
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
  node.addEventListener("mouseenter", (e) => {
    const t = tip();
    t.innerHTML = html;
    t.style.opacity = 1;
    move(e);
  });
  node.addEventListener("mousemove", move);
  node.addEventListener("mouseleave", () => (tip().style.opacity = 0));
  function move(e) {
    const t = tip();
    t.style.left = `${Math.min(e.clientX + 14, window.innerWidth - 300)}px`;
    t.style.top = `${e.clientY + 14}px`;
  }
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
  draw();
  document.querySelector("#dl-csv").addEventListener("click", exportCsv);
  document.querySelector("#dl-png").addEventListener("click", exportPng);
}

main();
