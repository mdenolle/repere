/* Repère board — cost-versus-quality with the convex-hull frontier.
 *
 * Reads data/leaderboard.json (schema v0.2). Separate from app.js, which draws
 * the skill-lift chart from a different file; the two answer different
 * questions and share only the palette.
 *
 * Three things this view exists to show that the lift chart cannot:
 *
 *   1. The frontier, per suite. A 1.00 on dv/v parameter choice and a 1.00 on
 *      literature retrieval are not the same achievement, so the hull is drawn
 *      inside each suite, never across them.
 *   2. The evidence behind each point. A row from one run is drawn hollow with
 *      no error bar; a row with repeats is filled and carries its interval.
 *   3. That the dollar frontier and the token frontier disagree.
 *
 * No chart library: hand-rolled SVG, same as app.js, so the page stays
 * dependency-free.
 */

const B_NS = "http://www.w3.org/2000/svg";

const B_MODEL_HEX = {
  "qwen2.5:7b": "#4b2e83",
  "llama3.1:8b": "#1b7f79",
  "deepseek-r1:7b": "#c2571a",
  "olmo2:7b": "#2f6fb2",
  "claude-haiku-4-5-20251001": "#8a1f5e",
};
const B_FALLBACK = "#6f6890";

const B_SUITE_LABEL = {
  codameter: "dv/v parameter choice",
  lit_rag: "Literature retrieval",
  synthetic_stalta: "STA/LTA code generation",
  orchestration: "Orchestration",
};

const B_AXES = {
  cost: {
    get: (r) => r.cost_usd,
    flag: "on_frontier_cost",
    label: "Cost per run (USD)",
    fmt: (v) => (v === 0 ? "$0" : `$${v.toFixed(4)}`),
    note: "Local open-weight models bill $0 in marginal dollars. That is true of dollars and false of cost — see the latency axis on the chart above.",
  },
  tokens: {
    get: (r) => r.total_tokens,
    flag: "on_frontier_tokens",
    label: "Total tokens per run",
    fmt: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)),
    note: "Tokens are the provider-independent axis: prices move under a published benchmark, so a reader can re-price these rows under a different list.",
  },
};

const bState = { rows: [], suite: null, axis: "cost", provenance: null };

const bEl = (n, attrs = {}, text = null) => {
  const e = document.createElementNS(B_NS, n);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== null) e.textContent = text;
  return e;
};

const bColor = (id) => B_MODEL_HEX[id] || B_FALLBACK;
const bSuites = () => [...new Set(bState.rows.map((r) => r.suite))].sort();

function bRowsForSuite() {
  return bState.rows.filter(
    (r) => r.suite === bState.suite && r.phase === "baseline" && Number.isFinite(B_AXES[bState.axis].get(r)),
  );
}

/* ----------------------------------------------------------------- drawing */
function bDraw() {
  const svg = document.querySelector("#board-chart");
  if (!svg) return;
  svg.replaceChildren();

  const narrow = window.innerWidth < 700;
  const W = narrow ? 420 : 900;
  const H = narrow ? 380 : 460;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const M = { top: 24, right: narrow ? 18 : 30, bottom: 58, left: narrow ? 52 : 64 };
  const PW = W - M.left - M.right;
  const PH = H - M.top - M.bottom;

  const ax = B_AXES[bState.axis];
  const rows = bRowsForSuite();
  const note = document.querySelector("#board-note");

  if (!rows.length) {
    svg.append(bEl("text", { x: W / 2, y: H / 2, "text-anchor": "middle", fill: "#6f6890" }, "No rows for this eval yet."));
    if (note) note.textContent = "";
    bTable([]);
    return;
  }

  // When every configuration in an eval costs $0 (all-local), a scaled axis
  // invents a range nobody paid. Collapse it to a nominal one and say so,
  // rather than drawing ticks up to $1.00 that mean nothing.
  const rawMax = Math.max(...rows.map(ax.get), 0);
  const allZero = rawMax === 0;
  const xMax = allZero ? 1 : rawMax * 1.2;
  const x = (v) => M.left + (v / xMax) * PW;
  const y = (v) => M.top + (1 - v) * PH;

  // grid + y ticks (score is always 0..1)
  for (let t = 0; t <= 1.0001; t += 0.2) {
    svg.append(bEl("line", { x1: M.left, x2: M.left + PW, y1: y(t), y2: y(t), stroke: "rgba(42,26,79,0.08)" }));
    svg.append(
      bEl("text", { x: M.left - 10, y: y(t) + 4, "text-anchor": "end", "font-size": 11, fill: "#6f6890" }, `${Math.round(t * 100)}%`),
    );
  }
  // x ticks
  if (allZero) {
    svg.append(
      bEl("text", { x: M.left + PW / 2, y: M.top + PH + 20, "text-anchor": "middle", "font-size": 11, fill: "#6f6890" },
        `every configuration in this eval: ${ax.fmt(0)}`),
    );
  } else {
    for (let i = 0; i <= 4; i++) {
      const v = (xMax / 4) * i;
      svg.append(bEl("text", { x: x(v), y: M.top + PH + 20, "text-anchor": "middle", "font-size": 11, fill: "#6f6890" }, ax.fmt(v)));
    }
  }
  svg.append(
    bEl("text", { x: M.left + PW / 2, y: H - 14, "text-anchor": "middle", "font-size": 12, fill: "#2a1a4f" }, ax.label),
  );
  svg.append(
    bEl("text", {
      x: 14, y: M.top + PH / 2, "text-anchor": "middle", "font-size": 12, fill: "#2a1a4f",
      transform: `rotate(-90 14 ${M.top + PH / 2})`,
    }, "Deterministic score"),
  );

  // The frontier: origin first, then the flagged rows cheapest-first. The
  // origin is on the hull because not deploying is always an option.
  const front = rows.filter((r) => r[ax.flag]).sort((a, b) => ax.get(a) - ax.get(b));
  if (front.length) {
    const pts = [[0, 0], ...front.map((r) => [ax.get(r), r.score_mean])];
    svg.append(
      bEl("polyline", {
        points: pts.map(([px, py]) => `${x(px)},${y(py)}`).join(" "),
        fill: "none", stroke: "#4b2e83", "stroke-width": 2, "stroke-dasharray": "6 4", opacity: 0.55,
      }),
    );
  }

  // Every local model bills exactly $0, so on the cost axis most of the board
  // collapses into one column and markers land on top of each other. Dodge
  // coincident x positions by a few pixels so each row stays visible. The
  // dodge is cosmetic and is stated in the note; the frontier is computed from
  // the real values, never from the dodged ones.
  const atX = new Map();
  for (const r of rows) {
    const key = ax.get(r);
    atX.set(key, (atX.get(key) || 0) + 1);
  }
  const dodgeSeen = new Map();
  const dodged = new Map();
  for (const r of rows) {
    const key = ax.get(r);
    const total = atX.get(key);
    if (total < 2) { dodged.set(r, 0); continue; }
    const i = dodgeSeen.get(key) || 0;
    dodgeSeen.set(key, i + 1);
    // With a collapsed axis every point shares x=0, so spread them across the
    // plot rather than stacking them in the first 60 pixels.
    dodged.set(r, allZero ? ((i + 0.5) / total) * PW : i * 11);
  }

  for (const r of rows) {
    // Clamp into the plot area: the $0 column is at the left edge, so an
    // unclamped dodge would push markers over the y-axis labels.
    const cx = Math.min(M.left + PW, Math.max(M.left + 4, x(ax.get(r)) + dodged.get(r)));
    const cy = y(r.score_mean);
    const hex = bColor(r.model_id);
    const repeated = (r.n_epochs || 1) > 1;

    if (repeated && r.score_ci95 > 0) {
      const top = y(Math.min(1, r.score_mean + r.score_ci95));
      const bot = y(Math.max(0, r.score_mean - r.score_ci95));
      svg.append(bEl("line", { x1: cx, x2: cx, y1: top, y2: bot, stroke: hex, "stroke-width": 1.5, opacity: 0.75 }));
      svg.append(bEl("line", { x1: cx - 4, x2: cx + 4, y1: top, y2: top, stroke: hex, "stroke-width": 1.5, opacity: 0.75 }));
      svg.append(bEl("line", { x1: cx - 4, x2: cx + 4, y1: bot, y2: bot, stroke: hex, "stroke-width": 1.5, opacity: 0.75 }));
    }

    // Hollow means a single run: a point estimate, not a measurement with an
    // interval. Filled means repeats. The distinction is the whole reason the
    // schema carries n_epochs.
    const marker = bEl("circle", {
      cx, cy, r: r[ax.flag] ? 7 : 5,
      fill: repeated ? hex : "#ffffff",
      stroke: hex,
      "stroke-width": r[ax.flag] ? 2.5 : 1.5,
      "stroke-dasharray": repeated ? "none" : "3 2",
    });
    marker.append(
      bEl("title", {}, [
        `${r.model_id} — ${r.agent_condition}`,
        `score ${(r.score_mean * 100).toFixed(2)}%${r.score_ci95 ? ` ± ${(r.score_ci95 * 100).toFixed(2)}pp` : ""}`,
        `${ax.label}: ${ax.fmt(ax.get(r))}`,
        repeated ? `${r.n_epochs} runs` : "1 run — no interval",
        r[ax.flag] ? "on the frontier" : "",
      ].filter(Boolean).join("\n")),
    );
    svg.append(marker);
  }

  if (note) {
    const single = rows.filter((r) => (r.n_epochs || 1) < 2).length;
    const parts = [ax.note];
    const stacked = [...atX.values()].some((n) => n > 1);
    if (stacked) parts.push("Markers sharing an x value are spread horizontally for legibility; the frontier uses the true values.");
    if (single) parts.push(`${single} of ${rows.length} rows come from a single run (hollow, dashed): point estimates with no interval.`);
    note.textContent = parts.join(" ");
  }
  bLegend(rows);
  bTable(rows);
}

function bLegend(rows) {
  const box = document.querySelector("#board-legend");
  if (!box) return;
  box.replaceChildren();
  const seen = new Set();
  for (const r of rows) {
    if (seen.has(r.model_id)) continue;
    seen.add(r.model_id);
    const item = document.createElement("span");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-swatch" style="background:${bColor(r.model_id)}"></span>${r.model_id}`;
    box.append(item);
  }
  const key = document.createElement("span");
  key.className = "legend-item";
  key.style.marginLeft = "12px";
  key.textContent = "large ring = on the frontier · dashed hollow = single run";
  box.append(key);
}

function bTable(rows) {
  const body = document.querySelector("#board-table-body");
  if (!body) return;
  body.replaceChildren();
  for (const r of [...rows].sort((a, b) => b.score_mean - a.score_mean)) {
    const tr = document.createElement("tr");
    const ci = r.score_ci95 ? ` ± ${(r.score_ci95 * 100).toFixed(2)}` : "";
    // Self-agreement across repeats. The scope suffix matters: "arm" is the
    // coarse whole-suite form, "record" the per-item one. Showing the number
    // without the scope would imply the finer measurement.
    const rel = r.reliability || {};
    const cons = Number.isFinite(rel.consistency_outcome)
      ? `${rel.consistency_outcome.toFixed(2)}${rel.consistency_scope ? ` (${rel.consistency_scope})` : ""}`
      : "—";
    const cells = [
      r.model_id,
      r.agent_condition,
      `${(r.score_mean * 100).toFixed(2)}${ci}`,
      String(r.n_epochs || 1),
      cons,
      r.cost_usd === 0 ? "$0" : `$${r.cost_usd.toFixed(4)}`,
      Number.isFinite(r.total_tokens) ? String(r.total_tokens) : "—",
      [r.on_frontier_cost ? "$" : "", r.on_frontier_tokens ? "tok" : ""].filter(Boolean).join(" + ") || "—",
    ];
    cells.forEach((text, i) => {
      const cell = document.createElement(i === 0 ? "th" : "td");
      if (i === 0) cell.setAttribute("scope", "row");
      cell.textContent = text;
      tr.append(cell);
    });
    body.append(tr);
  }
}

/* ----------------------------------------------------------------- controls */
function bControls() {
  const tabs = document.querySelector("#board-suites");
  if (tabs) {
    tabs.replaceChildren();
    for (const s of bSuites()) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.setAttribute("aria-pressed", String(s === bState.suite));
      b.textContent = B_SUITE_LABEL[s] || s;
      b.addEventListener("click", () => { bState.suite = s; bControls(); bDraw(); });
      tabs.append(b);
    }
  }
  const axes = document.querySelector("#board-axis");
  if (axes) {
    axes.replaceChildren();
    for (const [key, ax] of Object.entries(B_AXES)) {
      const usable = bState.rows.some((r) => Number.isFinite(ax.get(r)));
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.setAttribute("aria-pressed", String(key === bState.axis));
      b.disabled = !usable;
      b.textContent = key === "cost" ? "Cost ($)" : "Tokens";
      if (!usable) b.title = "not yet measured";
      b.addEventListener("click", () => { bState.axis = key; bControls(); bDraw(); });
      axes.append(b);
    }
  }
}

function bProvenance(payload) {
  const box = document.querySelector("#board-provenance");
  if (!box) return;
  const p = payload.provenance;
  const bits = [];
  if (payload.generated_at) bits.push(`Generated ${new Date(payload.generated_at).toLocaleString(undefined, { dateStyle: "medium" })}`);
  if (p?.harness_commit) bits.push(`harness ${String(p.harness_commit).slice(0, 7)}${p.harness_dirty ? " (dirty tree)" : ""}`);
  if (p?.host?.host_id) bits.push(`host ${p.host.host_id}${p.host.label ? ` (${p.host.label})` : ""}`);
  if (p?.models?.length) {
    const unpinned = p.unpinned_models || [];
    bits.push(unpinned.length ? `${unpinned.length} model(s) not pinned by digest` : "all model weights pinned by digest");
  }
  box.textContent = bits.join(" · ");

  const warn = document.querySelector("#board-warnings");
  if (!warn) return;
  const warnings = p?.warnings || [];
  if (!warnings.length) { warn.hidden = true; return; }
  warn.hidden = false;
  warn.replaceChildren();
  for (const w of warnings) {
    const li = document.createElement("li");
    li.textContent = w;
    warn.append(li);
  }
}

async function bMain() {
  let payload;
  try {
    const res = await fetch("data/leaderboard.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();
  } catch (err) {
    const note = document.querySelector("#board-note");
    if (note) note.textContent = `Could not load the board: ${err.message}`;
    return;
  }
  bState.rows = payload.leaderboard || [];
  bState.suite = bSuites()[0] || null;
  bProvenance(payload);
  bControls();
  bDraw();

  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(bDraw, 150); });
}

bMain();
