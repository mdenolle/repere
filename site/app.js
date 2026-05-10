const formatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});

const currencyFormatter = new Intl.NumberFormat(undefined, {
  currency: "USD",
  maximumFractionDigits: 4,
  style: "currency",
});

function formatScore(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${percentFormatter.format(value * 100)}%`;
}

function formatLift(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${percentFormatter.format(value * 100)} pp`;
}

function formatCost(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  if (value === 0) return "$0.0000";
  return currencyFormatter.format(value);
}

function formatCostDelta(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${percentFormatter.format(value)}%`;
}

function formatEfficiency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return formatter.format(value);
}

function formatDate(value) {
  if (!value) return "Generated date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return `Updated ${parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
}

// Map AstaBench-style openness/toolset categories to short pill labels and CSS classes.
const OPENNESS_LABELS = {
  "open-source-open-weight": { short: "open weights", cls: "pill pill-open" },
  "open-source-closed-weight": { short: "open code", cls: "pill pill-mixed" },
  "closed-source-api": { short: "API only", cls: "pill pill-closed" },
  "closed-source-ui": { short: "UI only", cls: "pill pill-closed" },
  unknown: { short: "unknown", cls: "pill pill-unknown" },
};
const TOOLSET_LABELS = {
  standard: { short: "standard", cls: "pill pill-toolset-standard" },
  "custom-interface": { short: "custom-iface", cls: "pill pill-toolset-iface" },
  custom: { short: "custom", cls: "pill pill-toolset-custom" },
  unknown: { short: "unknown", cls: "pill pill-unknown" },
};

function appendPill(td, value, lookup) {
  const meta = lookup[value] ?? lookup.unknown;
  const span = document.createElement("span");
  span.className = meta.cls;
  span.textContent = meta.short;
  span.title = value ?? "unknown";
  td.appendChild(span);
}

// computeParetoFront — returns the indices of rows on the cost-vs-quality
// Pareto front. A row is dominated when some other row has both
// score >= a.score AND cost_usd <= a.cost_usd, with at least one strict
// inequality. Non-dominated rows are on the front.
function computeParetoFront(rows) {
  const front = [];
  for (let i = 0; i < rows.length; i++) {
    const a = rows[i];
    const ascore = Number(a.score);
    const acost = Number(a.cost_usd);
    let dominated = false;
    for (let j = 0; j < rows.length; j++) {
      if (i === j) continue;
      const b = rows[j];
      const bscore = Number(b.score);
      const bcost = Number(b.cost_usd);
      const betterOrEqualScore = bscore >= ascore;
      const lowerOrEqualCost = bcost <= acost;
      const strictlyBetter = bscore > ascore || bcost < acost;
      if (betterOrEqualScore && lowerOrEqualCost && strictlyBetter) {
        dominated = true;
        break;
      }
    }
    if (!dominated) front.push(i);
  }
  return new Set(front);
}

function renderSummary(rows) {
  const best = rows.reduce((current, row) => (row.score > (current?.score ?? -1) ? row : current), null);
  const lowest = rows.reduce(
    (current, row) => (row.cost_usd < (current?.cost_usd ?? Number.POSITIVE_INFINITY) ? row : current),
    null,
  );
  const modelCount = new Set(rows.map((row) => row.model_id)).size;

  document.querySelector("#best-score").textContent = best ? formatScore(best.score) : "—";
  document.querySelector("#lowest-cost").textContent = lowest ? formatCost(lowest.cost_usd) : "—";
  document.querySelector("#model-count").textContent = `${modelCount}`;
}

function renderTable(rows) {
  const body = document.querySelector("#leaderboard-body");
  body.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="10" class="empty">No leaderboard rows published yet.</td>';
    body.appendChild(tr);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const textCells = [
      { className: "rank", value: `#${row.rank}` },
      { className: "model", value: row.model_id },
      { value: row.agent_condition ?? "generic-coding-agent" },
    ];
    for (const cell of textCells) {
      const td = document.createElement("td");
      if (cell.className) td.className = cell.className;
      td.textContent = cell.value;
      tr.appendChild(td);
    }
    // Openness pill
    const opennessTd = document.createElement("td");
    appendPill(opennessTd, row.openness ?? "unknown", OPENNESS_LABELS);
    tr.appendChild(opennessTd);
    // Toolset pill
    const toolsetTd = document.createElement("td");
    appendPill(toolsetTd, row.toolset ?? "unknown", TOOLSET_LABELS);
    tr.appendChild(toolsetTd);

    const trailing = [
      { value: row.suite },
      { className: "score", value: formatScore(row.score) },
      { className: "mono", value: formatCost(row.cost_usd) },
      { className: "mono", value: `${row.n_completed}/${row.n_total}` },
      { className: "mono", value: formatEfficiency(row.efficiency_score) },
    ];
    for (const cell of trailing) {
      const td = document.createElement("td");
      if (cell.className) td.className = cell.className;
      td.textContent = cell.value;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function renderSkillLiftTable(rows) {
  const body = document.querySelector("#skill-lift-body");
  if (!body) return;
  body.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="11" class="empty">No skill-lift rows published yet.</td>';
    body.appendChild(tr);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    // Model id (text)
    const modelTd = document.createElement("td");
    modelTd.className = "model";
    modelTd.textContent = row.model_id;
    tr.appendChild(modelTd);
    // Openness pill
    const opennessTd = document.createElement("td");
    appendPill(opennessTd, row.openness ?? "unknown", OPENNESS_LABELS);
    tr.appendChild(opennessTd);
    // Toolset pill
    const toolsetTd = document.createElement("td");
    appendPill(toolsetTd, row.toolset ?? "unknown", TOOLSET_LABELS);
    tr.appendChild(toolsetTd);
    // Trailing text cells
    const trailing = [
      { value: `${row.skill_name} ${row.skill_version}` },
      { value: row.suite },
      { className: "mono", value: formatScore(row.score_none) },
      { className: "score", value: formatScore(row.score_full) },
      { className: "mono", value: formatLift(row.lift) },
      { className: "mono", value: formatCost(row.cost_none_usd) },
      { className: "mono", value: formatCost(row.cost_full_usd) },
      { className: "mono", value: formatCostDelta(row.cost_lift_pct) },
    ];
    for (const cell of trailing) {
      const td = document.createElement("td");
      if (cell.className) td.className = cell.className;
      td.textContent = cell.value;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

// Render the cost-vs-quality scatter into #pareto-canvas using Chart.js.
// Pareto-front points are highlighted (solid, larger, connected by a line);
// dominated points are faded.
function renderParetoChart(rows) {
  const canvas = document.querySelector("#pareto-canvas");
  if (!canvas || typeof Chart === "undefined") return;
  if (window._frugalmindParetoChart) {
    window._frugalmindParetoChart.destroy();
  }
  if (!rows.length) return;

  const front = computeParetoFront(rows);
  const points = rows.map((r, i) => ({
    x: Number(r.cost_usd),
    y: Number(r.score) * 100,
    label: r.model_id,
    condition: r.agent_condition,
    onFront: front.has(i),
  }));

  const frontPoints = points
    .filter((p) => p.onFront)
    .slice()
    .sort((a, b) => a.x - b.x);

  const dominatedPoints = points.filter((p) => !p.onFront);

  // Inherit text/border colors from CSS variables so dark mode works.
  const cssVar = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || undefined;
  const textColor = cssVar("--color-text-primary") || "#1a1a1a";
  const subtleColor = cssVar("--color-text-secondary") || "#6b7280";
  const borderColor = cssVar("--color-border-tertiary") || "#e5e7eb";

  window._frugalmindParetoChart = new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Pareto front",
          data: frontPoints,
          backgroundColor: "rgba(31, 111, 61, 0.85)",
          borderColor: "rgba(31, 111, 61, 1)",
          pointRadius: 6,
          pointHoverRadius: 8,
          showLine: true,
          borderWidth: 2,
          tension: 0,
        },
        {
          label: "Dominated",
          data: dominatedPoints,
          backgroundColor: "rgba(136, 135, 128, 0.35)",
          borderColor: "rgba(136, 135, 128, 0.5)",
          pointRadius: 4,
          pointHoverRadius: 6,
          showLine: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: textColor, boxWidth: 14 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const p = ctx.raw;
              return `${p.label} (${p.condition}) — ${p.y.toFixed(1)}% @ ${formatCost(p.x)}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Cost per run (USD)", color: subtleColor },
          ticks: { color: subtleColor, callback: (v) => formatCost(Number(v)) },
          grid: { color: borderColor },
        },
        y: {
          title: { display: true, text: "Quality (%)", color: subtleColor },
          ticks: { color: subtleColor, callback: (v) => `${v}%` },
          grid: { color: borderColor },
          min: 0,
          max: 100,
        },
      },
    },
  });
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load ${path}: ${response.status}`);
  }
  return response.json();
}

async function loadLeaderboard() {
  return loadJson("data/leaderboard.json");
}

async function loadSkillLift() {
  try {
    return await loadJson("data/skill_lift.json");
  } catch (error) {
    return { rows: [], generated_at: null, source: null, notes: [error.message] };
  }
}

async function main() {
  const generatedAt = document.querySelector("#generated-at");
  const sourceLabel = document.querySelector("#source-label");
  const notes = document.querySelector("#leaderboard-notes");
  const skillGeneratedAt = document.querySelector("#skill-lift-generated-at");
  const skillSourceLabel = document.querySelector("#skill-lift-source-label");
  const skillNotes = document.querySelector("#skill-lift-notes");
  const paretoGeneratedAt = document.querySelector("#pareto-generated-at");
  const paretoSourceLabel = document.querySelector("#pareto-source-label");
  const paretoNotes = document.querySelector("#pareto-notes");

  // Main leaderboard.
  let leaderboardRows = [];
  try {
    const data = await loadLeaderboard();
    leaderboardRows = data.leaderboard ?? [];
    generatedAt.textContent = formatDate(data.generated_at);
    sourceLabel.textContent = data.source ?? "data/leaderboard.json";
    notes.textContent = (data.notes ?? []).join(" ");
    renderSummary(leaderboardRows);
    renderTable(leaderboardRows);
    if (paretoGeneratedAt) paretoGeneratedAt.textContent = formatDate(data.generated_at);
    if (paretoSourceLabel) paretoSourceLabel.textContent = data.source ?? "data/leaderboard.json";
    if (paretoNotes) {
      const front = computeParetoFront(leaderboardRows);
      paretoNotes.textContent = `${front.size}/${leaderboardRows.length} rows on the Pareto front.`;
    }
  } catch (error) {
    generatedAt.textContent = "Leaderboard unavailable";
    notes.textContent = error.message;
    renderSummary([]);
    renderTable([]);
    if (paretoNotes) paretoNotes.textContent = error.message;
  }

  // Pareto chart depends on Chart.js, which is loaded via `defer`.
  // If the script hasn't finished by the time we get here, retry once on load.
  const drawChart = () => renderParetoChart(leaderboardRows);
  if (typeof Chart === "undefined") {
    window.addEventListener("load", drawChart, { once: true });
  } else {
    drawChart();
  }

  // Skill-lift table.
  const skillData = await loadSkillLift();
  const skillRows = skillData.rows ?? [];
  if (skillGeneratedAt) skillGeneratedAt.textContent = formatDate(skillData.generated_at);
  if (skillSourceLabel) skillSourceLabel.textContent = skillData.source ?? "data/skill_lift.json";
  if (skillNotes) skillNotes.textContent = (skillData.notes ?? []).join(" ");
  renderSkillLiftTable(skillRows);
}

main();
