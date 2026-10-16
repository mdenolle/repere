/* Executes board.js against a DOM stub and the committed leaderboard.json.
 *
 * The question this answers: does the board actually draw, with the frontier,
 * from the real data file? A chart that silently renders nothing looks the same
 * as one nobody visited.
 */
import fs from "fs";

const made = [];
function node(name) {
  return {
    tag: name, children: [], attrs: {}, style: {}, _text: "", hidden: false,
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.children.push(c)); },
    replaceChildren() { this.children = []; },
    addEventListener() {},
    set innerHTML(v) { this.children = []; },
    set textContent(v) { this._text = v; },
    get textContent() { return this._text; },
  };
}
const store = {};
globalThis.document = {
  createElementNS(_ns, n) { const e = node(n); made.push(e); return e; },
  createElement(n) { const e = node(n); made.push(e); return e; },
  querySelector(sel) { return (store[sel] ||= node("div")); },
  addEventListener() {},
};
globalThis.window = {
  innerWidth: Number(process.env.REPERE_VW) || 1200,
  addEventListener() {},
};
globalThis.fetch = async (path) => ({
  ok: true,
  json: async () => JSON.parse(fs.readFileSync("site/data/" + path.split("/").pop(), "utf8")),
});

fs.writeFileSync("/tmp/_board_test.mjs", fs.readFileSync("site/board.js", "utf8"));
try { await import("/tmp/_board_test.mjs"); } catch (e) { console.error("IMPORT ERROR:", e.message); process.exit(1); }
await new Promise((r) => setTimeout(r, 300));

const counts = made.reduce((a, e) => ((a[e.tag] = (a[e.tag] || 0) + 1), a), {});
console.log("SVG elements drawn:", JSON.stringify(counts));
console.log("viewBox:", store["#board-chart"]?.attrs?.viewBox || "(none)");
console.log("note:", (store["#board-note"]?.textContent || "").slice(0, 110));
console.log("provenance:", (store["#board-provenance"]?.textContent || "").slice(0, 110));
console.log("table rows:", store["#board-table-body"]?.children.length ?? 0);

// Proportional to the data, not a hardcoded count: the board must draw one
// marker per baseline row of whichever suite is shown first, and one frontier.
const payload = JSON.parse(fs.readFileSync("site/data/leaderboard.json", "utf8"));
const baseline = (payload.leaderboard || []).filter((r) => r.phase === "baseline");
const firstSuite = [...new Set(baseline.map((r) => r.suite))].sort()[0];
const expected = baseline.filter((r) => r.suite === firstSuite).length;
const markers = counts.circle || 0;
const frontier = counts.polyline || 0;
const tableRows = store["#board-table-body"]?.children.length ?? 0;
console.log(`suite "${firstSuite}": ${expected} rows · ${markers} markers · ${tableRows} table rows`);
const ok = expected > 0 && markers >= expected && frontier >= 1 && tableRows >= expected;
console.log(ok ? "✅ BOARD RENDERS (markers + frontier + table)" : "❌ BOARD EMPTY");
process.exit(ok ? 0 : 1);
