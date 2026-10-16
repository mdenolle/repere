import fs from "fs";
// Minimal DOM/SVG stub — enough to execute draw() for real.
const made = [];
function node(name) {
  return {
    tag: name, children: [], attrs: {}, style: {}, _text: "",
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {},
    insertBefore(c) { this.children.unshift(c); },
    set innerHTML(v) { this.children = []; },
    set textContent(v) { this._text = v; },
    get textContent() { return this._text; },
  };
}
const store = {};
globalThis.document = {
  createElementNS(_ns, n) { const e = node(n); made.push(e); return e; },
  createElement(n) { const e = node(n); made.push(e); return e; },
  createTextNode(t) { return node("#text"); },
  querySelector(sel) { return (store[sel] ||= node("div")); },
  addEventListener() {},
};
globalThis.window = {
  innerWidth: Number(process.env.REPERE_VW) || 1200,
  innerHeight: Number(process.env.REPERE_VH) || 900,
  addEventListener() {},
};
globalThis.fetch = async (path) => ({
  ok: true,
  json: async () => JSON.parse(fs.readFileSync("site/data/" + path.split("/").pop(), "utf8")),
});

const src = fs.readFileSync("site/app.js", "utf8");
fs.writeFileSync("/tmp/_app_test.mjs", src);
try { await import("/tmp/_app_test.mjs"); } catch (e) { console.error("IMPORT ERROR:", e.message); process.exit(1); }
await new Promise((r) => setTimeout(r, 300));

const counts = made.reduce((a, e) => ((a[e.tag] = (a[e.tag] || 0) + 1), a), {});
console.log("SVG elements drawn:", JSON.stringify(counts));
const vb = (store["#chart"] && store["#chart"].attrs && store["#chart"].attrs.viewBox) || "";
console.log("viewBox:", vb);
const note = store["#chart-note"]?.textContent || "";
console.log("chart note:", note.slice(0, 70));
// Expect two markers per row (no-skill and skill), not a hardcoded count. The
// threshold used to be `>= 20`, which silently encoded the size of the July
// dataset: a smaller but perfectly valid board then failed as though the chart
// were broken.
const nRows = JSON.parse(fs.readFileSync("site/data/skill_lift.json", "utf8")).rows.length;
const markers = (counts.circle || 0) + (counts.rect || 0) + (counts.polygon || 0) + (counts.path || 0);
const expected = 2 * nRows;
console.log(`rows: ${nRows} · markers drawn: ${markers} (expected >= ${expected})`);
const ok = nRows > 0 && markers >= expected && (counts.line || 0) > 0;
console.log(ok ? "✅ CHART RENDERS (markers + lift lines present)" : "❌ CHART EMPTY");
process.exit(ok ? 0 : 1);
