"""Handpick: build a local grading tool, one HTML file, no server, assisted but blind.

The file embeds the items, the rubric and its hash, and shuffles the order with a recorded seed.
Every dimension of the rubric is on the item's page. Context fields (a fact sheet, a packet, a
brief) are shown before labeling. Hidden fields, one per dimension such as a judge's score and
rationale, are stored encoded and rendered only after the blind labels for that item are
committed; a revised label per dimension is stored separately. Export writes one label row per
item and dimension, the shape ``prospect`` reads.

    from motherlode.grading import build_grading_tool
    build_grading_tool(items, spec, "grade.html", context_keys=["packet"], hidden_prefix="judge_",
                       rater="zachary", title="Trade desk pilot")

Each item is a dict with an ``id``, a ``text``, any context keys, and hidden fields named
``<hidden_prefix><dimension id>``. A single-label rubric is a spec with one dimension.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
from collections.abc import Sequence
from pathlib import Path

from .rubric import RubricSpec, rubric_hash as _rubric_hash, single_label_spec


def rubric_hash(rubric_text: str, spec: RubricSpec | None = None) -> str:
    return _rubric_hash(rubric_text, spec)


def build_grading_tool(
    items: Sequence[dict],
    spec: RubricSpec | str,
    out_path: Path | str,
    labels: Sequence[str] | None = None,
    context_keys: Sequence[str] = (),
    hidden_keys: Sequence[str] = (),
    hidden_prefix: str | None = None,
    rater: str = "rater",
    title: str = "Handpick",
    seed: int = 0,
    glossary: dict[str, str] | None = None,
    glossary_title: str = "Glossary",
) -> Path:
    """``spec`` is a RubricSpec, or rubric text with ``labels`` for the single-label case.

    Hidden fields: with ``hidden_prefix`` the tool reveals ``<prefix><dimension>`` beside each
    dimension after commit; ``hidden_keys`` names item-level fields revealed together. Both may
    be used.
    """
    if isinstance(spec, str):
        if not labels:
            raise ValueError("a text rubric needs labels; pass a RubricSpec for several dimensions")
        spec = single_label_spec(labels, spec)
    for it in items:
        if "id" not in it or "text" not in it:
            raise ValueError("every item needs an 'id' and a 'text'")
    rh = spec.hash
    public, hidden = [], {}
    for it in items:
        public.append({"id": str(it["id"]), "text": it["text"], **{k: it.get(k, "") for k in context_keys}})
        h = {k: it.get(k, "") for k in hidden_keys}
        if hidden_prefix:
            for d in spec.dimensions:
                h[f"{hidden_prefix}{d.id}"] = it.get(f"{hidden_prefix}{d.id}", "")
        hidden[str(it["id"])] = h
    hidden_b64 = base64.b64encode(json.dumps(hidden, ensure_ascii=False).encode("utf-8")).decode("ascii")
    tool_id = hashlib.sha256(f"{title}|{rh}|{rater}|{seed}".encode()).hexdigest()[:8]
    payload = {
        "title": title, "rater": rater, "rubric_hash": rh, "seed": seed, "tool_id": tool_id,
        "dimensions": [{"id": d.id, "name": d.name or d.id, "labels": d.labels()} for d in spec.dimensions],
        "context_keys": list(context_keys), "hidden_keys": list(hidden_keys), "hidden_prefix": hidden_prefix or "",
        "glossary": glossary or {}, "glossary_title": glossary_title, "items": public,
    }
    doc = (_TEMPLATE.replace("__TITLE__", html.escape(title))
           .replace("__RUBRIC__", html.escape(spec.text))
           .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__HIDDEN__", hidden_b64))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --ink:#1c2128; --muted:#6b7480; --rule:#d8ddd4; --accent:#23645f; --soft:#e3eeeb; --warn:#7a5a1e; --warnbg:#f3ebdd; --bg:#f4f6f2; }
  body { margin:0; background:var(--bg); color:var(--ink); font: 16px/1.5 Georgia, serif; padding: 20px; }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { font: 600 22px/1.2 system-ui, sans-serif; margin: 0 0 4px; }
  .meta { font: 12.5px ui-monospace, monospace; color: var(--muted); margin-bottom: 18px; }
  .card { background:#fff; border:1px solid var(--rule); border-radius:6px; padding:16px 18px; margin: 12px 0; }
  .k { font: 600 12px system-ui, sans-serif; letter-spacing:.06em; text-transform: uppercase; color: var(--muted); margin: 0 0 6px; }
  .text { font-size: 18px; }
  pre { white-space: pre-wrap; font: 13.5px ui-monospace, monospace; background: var(--soft); padding: 10px 12px; border-radius: 4px; margin: 0; max-height: 60vh; overflow: auto; }
  details summary { cursor: pointer; font: 600 14px system-ui, sans-serif; color: var(--accent); }
  .dim { display: grid; grid-template-columns: 220px 1fr; gap: 8px 14px; align-items: center; padding: 8px 0; border-top: 1px solid var(--rule); }
  .dim .name { font: 600 14px system-ui, sans-serif; }
  .labels button { font: 600 14px system-ui, sans-serif; padding: 6px 12px; margin: 2px 6px 2px 0; border: 1.5px solid var(--rule); background:#fff; border-radius: 4px; cursor:pointer; }
  .labels button.on { background: var(--accent); color:#fff; border-color: var(--accent); }
  .labels button:disabled { cursor: default; opacity: .8; }
  .hidden { display:none; }
  .revealed { border-left: 3px solid var(--warn); background: var(--warnbg); }
  .rev { font: 13.5px system-ui, sans-serif; color: var(--warn); margin: 4px 0 0; }
  .nav button, .top button { font: 14px system-ui, sans-serif; padding: 6px 12px; margin-right: 8px; cursor:pointer; }
  .prog { font: 13px ui-monospace, monospace; color: var(--muted); }
  textarea { width: 100%; box-sizing: border-box; font: 14px system-ui, sans-serif; min-height: 48px; }
  @media (max-width: 600px) { .dim { grid-template-columns: 1fr; } }
</style></head><body><div class="wrap">
<h1 id="title"></h1>
<div class="meta" id="meta"></div>
<div class="top"><button id="prev">← prev</button><button id="next">next →</button><button id="export">export JSONL</button><span class="prog" id="prog"></span></div>
<details class="card"><summary>Rubric (frozen; hash recorded in every label)</summary><pre>__RUBRIC__</pre></details>
<details class="card" id="glossary-card"><summary id="glossary-title"></summary><div id="glossary"></div></details>
<div id="item"></div>
<script>
const P = __PAYLOAD__;
const HIDDEN_B64 = "__HIDDEN__";
let HIDDEN = null;
function hidden() { if (!HIDDEN) HIDDEN = JSON.parse(decodeURIComponent(escape(atob(HIDDEN_B64)))); return HIDDEN; }
function rng(seed){ return function(){ seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; }; }
const order = P.items.map((_,i)=>i); const r = rng(P.seed); for (let i=order.length-1;i>0;i--){ const j=Math.floor(r()*(i+1)); [order[i],order[j]]=[order[j],order[i]]; }
const KEY = "motherlode-handpick-" + P.tool_id;
let store = {}; try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e) { store = {}; }
function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); } catch(e) {} }
let pos = 0;
document.getElementById("title").textContent = P.title;
document.getElementById("meta").textContent = `rater ${P.rater} · rubric ${P.rubric_hash} · seed ${P.seed} · tool ${P.tool_id} · ${P.items.length} items · labels saved in this browser`;
const g = document.getElementById("glossary"); document.getElementById("glossary-title").textContent = P.glossary_title;
if (Object.keys(P.glossary).length===0) document.getElementById("glossary-card").classList.add("hidden");
for (const [k,v] of Object.entries(P.glossary)) { const d=document.createElement("div"); d.innerHTML = "<b>"+esc(k)+"</b>: "+esc(v); g.appendChild(d); }
function esc(s){ return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function complete(rec){ return P.dimensions.every(d => rec.blind && rec.blind[d.id] !== undefined); }
function render(){
  const it = P.items[order[pos]]; const rec = store[it.id] || {blind:{}, revealed:{}};
  const el = document.getElementById("item"); let h = "";
  h += `<div class="card"><p class="k">Item ${pos+1} of ${P.items.length}</p>` + (it.text.includes("\n") ? `<pre>${esc(it.text)}</pre>` : `<div class="text">${esc(it.text)}</div>`) + `</div>`;
  for (const k of P.context_keys) { if (it[k]) h += `<div class="card"><p class="k">${esc(k.replace(/_/g," "))}</p><pre>${esc(it[k])}</pre></div>`; }
  h += `<div class="card"><p class="k">Blind labels</p>`;
  for (const d of P.dimensions) {
    h += `<div class="dim"><div class="name">${esc(d.id)} ${esc(d.name)}</div><div class="labels" data-dim="${esc(d.id)}">` +
      d.labels.map(l=>`<button data-l="${esc(l)}" class="${(rec.blind||{})[d.id]===l?"on":""}" ${rec.committed?"disabled":""}>${esc(l)}</button>`).join("") + `</div></div>`;
  }
  h += `<p class="k" style="margin-top:10px">Note</p><textarea id="note">${esc(rec.note||"")}</textarea>`;
  h += `<div style="margin-top:10px"><button id="commit" ${complete(rec)&&!rec.committed?"":"disabled"}>${rec.committed?"committed":"commit blind labels"}</button></div></div>`;
  if (rec.committed) {
    const hid = hidden()[it.id] || {};
    h += `<div class="card revealed"><p class="k">Revealed after commit</p>`;
    for (const k of P.hidden_keys) h += `<p><b>${esc(k.replace(/_/g," "))}</b>: ${esc(hid[k]||"")}</p>`;
    for (const d of P.dimensions) {
      const hk = P.hidden_prefix ? P.hidden_prefix + d.id : null;
      h += `<div class="dim"><div class="name">${esc(d.id)} ${esc(d.name)}<div class="rev">you: ${esc((rec.blind||{})[d.id])}${hk && hid[hk] ? " · hidden: " + esc(hid[hk]) : ""}</div></div>` +
        `<div class="labels" data-rev="${esc(d.id)}">` + d.labels.map(l=>`<button data-l="${esc(l)}" class="${(rec.revealed||{})[d.id]===l?"on":""}">${esc(l)}</button>`).join("") + `</div></div>`;
    }
    h += `<p class="rev">Revised labels are optional and stored separately from the blind ones.</p></div>`;
  }
  el.innerHTML = h;
  el.querySelectorAll(".labels[data-dim] button").forEach(b=>b.onclick=()=>{ if (rec.committed) return; const cur = store[it.id] || {blind:{}, revealed:{}}; cur.blind = {...(cur.blind||{}), [b.parentElement.dataset.dim]: b.dataset.l}; store[it.id]=cur; save(); render(); });
  el.querySelectorAll(".labels[data-rev] button").forEach(b=>b.onclick=()=>{ const cur = store[it.id]; cur.revealed = {...(cur.revealed||{}), [b.parentElement.dataset.rev]: b.dataset.l}; cur.revealed_ts = new Date().toISOString(); store[it.id]=cur; save(); render(); });
  const note = el.querySelector("#note"); note.oninput = ()=>{ const cur = store[it.id] || {blind:{}, revealed:{}}; cur.note = note.value; store[it.id]=cur; save(); };
  const c = el.querySelector("#commit"); if (c) c.onclick = ()=>{ const cur = store[it.id]; if (!cur || !complete(cur)) return; cur.committed = true; cur.blind_ts = new Date().toISOString(); store[it.id]=cur; save(); render(); };
  const done = P.items.filter(x=>store[x.id]&&store[x.id].committed).length;
  document.getElementById("prog").textContent = `${done} committed`;
}
document.getElementById("prev").onclick=()=>{ pos=(pos-1+P.items.length)%P.items.length; render(); };
document.getElementById("next").onclick=()=>{ pos=(pos+1)%P.items.length; render(); };
document.getElementById("export").onclick=()=>{
  const rows=[]; for (const it of P.items){ const rec=store[it.id]; if(!rec||!rec.committed) continue;
    for (const d of P.dimensions) {
      rows.push(JSON.stringify({item_id:it.id, rater:P.rater, dimension:d.id, label:rec.blind[d.id], rubric_hash:P.rubric_hash, pass:"blind", ts:rec.blind_ts, note:rec.note||""}));
      if (rec.revealed && rec.revealed[d.id] !== undefined) rows.push(JSON.stringify({item_id:it.id, rater:P.rater, dimension:d.id, label:rec.revealed[d.id], rubric_hash:P.rubric_hash, pass:"revealed", ts:rec.revealed_ts}));
    }
  }
  const blob=new Blob([rows.join("\n")+"\n"],{type:"application/jsonl"}); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=`labels-${P.rater}-${P.tool_id}.jsonl`; a.click();
};
render();
</script></div></body></html>
"""
