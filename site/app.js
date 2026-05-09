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

  // Main leaderboard.
  try {
    const data = await loadLeaderboard();
    const rows = data.leaderboard ?? [];
    generatedAt.textContent = formatDate(data.generated_at);
    sourceLabel.textContent = data.source ?? "data/leaderboard.json";
    notes.textContent = (data.notes ?? []).join(" ");
    renderSummary(rows);
    renderTable(rows);
  } catch (error) {
    generatedAt.textContent = "Leaderboard unavailable";
    notes.textContent = error.message;
    renderSummary([]);
    renderTable([]);
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
