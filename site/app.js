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

function formatCost(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  if (value === 0) return "$0.0000";
  return currencyFormatter.format(value);
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
    tr.innerHTML = '<td colspan="7" class="empty">No leaderboard rows published yet.</td>';
    body.appendChild(tr);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const cells = [
      { className: "rank", value: `#${row.rank}` },
      { className: "model", value: row.model_id },
      { value: row.suite },
      { className: "score", value: formatScore(row.score) },
      { className: "mono", value: formatCost(row.cost_usd) },
      { className: "mono", value: `${row.n_completed}/${row.n_total}` },
      { className: "mono", value: formatEfficiency(row.efficiency_score) },
    ];

    for (const cell of cells) {
      const td = document.createElement("td");
      if (cell.className) td.className = cell.className;
      td.textContent = cell.value;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

async function loadLeaderboard() {
  const response = await fetch("data/leaderboard.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load leaderboard data: ${response.status}`);
  }
  return response.json();
}

async function main() {
  const generatedAt = document.querySelector("#generated-at");
  const sourceLabel = document.querySelector("#source-label");
  const notes = document.querySelector("#leaderboard-notes");

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
}

main();
