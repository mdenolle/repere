import fs from "fs";
const made = [];
function node(name) {
  return { tag: name, children: [], attrs: {}, style: {}, _text: "", className: "",
    setAttribute(k,v){this.attrs[k]=v;}, appendChild(c){this.children.push(c);return c;},
    addEventListener(){}, insertBefore(c){this.children.unshift(c);},
    set innerHTML(v){this.children=[];}, set textContent(v){this._text=v;}, get textContent(){return this._text;} };
}
const store = {};
globalThis.document = {
  createElementNS(_n,n){const e=node(n);made.push(e);return e;},
  createElement(n){const e=node(n);made.push(e);return e;},
  createTextNode(t){const e=node("#text");e._text=t;return e;},
  querySelector(s){return (store[s] ||= node("div"));},
};
globalThis.window={innerWidth:1200};
globalThis.fetch=async(p)=>({ok:true,json:async()=>JSON.parse(fs.readFileSync("site/data/"+p.split("/").pop(),"utf8"))});
fs.writeFileSync("/tmp/_app2.mjs", fs.readFileSync("site/app.js","utf8"));
await import("/tmp/_app2.mjs");
await new Promise(r=>setTimeout(r,300));

const legend = store["#legend"];
function text(n){ return n._text || n.children.map(text).join(""); }
for (const grp of legend.children) {
  const title = grp.children[0]?._text ?? "?";
  const items = grp.children.slice(1).map(text);
  console.log(`  [${title}]`);
  for (const i of items) console.log(`      • ${i}`);
}
