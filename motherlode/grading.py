"""Build a local grading tool: one HTML file, no server, assisted but blind.

The file embeds the items, the rubric and its hash, shuffles the order with a recorded seed, and
saves labels in the browser as the grader works. Context fields (a fact sheet, a glossary, a
brief) are shown before labeling. Hidden fields (a judge's verdict and rationale) are stored
encoded and rendered only after the blind label is committed; a second, revealed pass records a
revision separately. Export writes JSONL rows the ``judge`` module reads directly.

    from motherlode.grading import build_grading_tool
    build_grading_tool(items, rubric_text, "grade.html", labels=["sound", "unsupported", "wrong facts", "vacuous"],
                       context_keys=["fact_sheet", "brief"], hidden_keys=["judge_label", "judge_rationale"],
                       rater="zachary", title="Pit wall reasons")

Each item is a dict with an ``id``, a ``text`` to grade, any context keys, and any hidden keys.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
from collections.abc import Sequence
from pathlib import Path


def rubric_hash(rubric_text: str) -> str:
    return hashlib.sha256(rubric_text.encode("utf-8")).hexdigest()[:12]


def build_grading_tool(
    items: Sequence[dict],
    rubric_text: str,
    out_path: Path | str,
    labels: Sequence[str],
    context_keys: Sequence[str] = (),
    hidden_keys: Sequence[str] = (),
    rater: str = "rater",
    title: str = "Grading",
    seed: int = 0,
    glossary: dict[str, str] | None = None,
) -> Path:
    for it in items:
        if "id" not in it or "text" not in it:
            raise ValueError("every item needs an 'id' and a 'text'")
    rh = rubric_hash(rubric_text)
    public = []
    hidden = {}
    for it in items:
        public.append({"id": str(it["id"]), "text": it["text"], **{k: it.get(k, "") for k in context_keys}})
        hidden[str(it["id"])] = {k: it.get(k, "") for k in hidden_keys}
    hidden_b64 = base64.b64encode(json.dumps(hidden, ensure_ascii=False).encode("utf-8")).decode("ascii")
    payload = {
        "title": title,
        "rater": rater,
        "rubric_hash": rh,
        "seed": seed,
        "labels": list(labels),
        "context_keys": list(context_keys),
        "hidden_keys": list(hidden_keys),
        "glossary": glossary or {},
        "items": public,
    }
    doc = _TEMPLATE.replace("__TITLE__", html.escape(title)) \
        .replace("__RUBRIC__", html.escape(rubric_text)) \
        .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")) \
        .replace("__HIDDEN__", hidden_b64)
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
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font: 600 22px/1.2 system-ui, sans-serif; margin: 0 0 4px; }
  .meta { font: 12.5px ui-monospace, monospace; color: var(--muted); margin-bottom: 18px; }
  .card { background:#fff; border:1px solid var(--rule); border-radius:6px; padding:16px 18px; margin: 12px 0; }
  .k { font: 600 12px system-ui, sans-serif; letter-spacing:.06em; text-transform: uppercase; color: var(--muted); margin: 0 0 6px; }
  .text { font-size: 18px; }
  pre { white-space: pre-wrap; font: 13.5px ui-monospace, monospace; background: var(--soft); padding: 10px 12px; border-radius: 4px; margin: 0; }
  details summary { cursor: pointer; font: 600 14px system-ui, sans-serif; color: var(--accent); }
  .labels button { font: 600 14px system-ui, sans-serif; padding: 8px 14px; margin: 4px 6px 4px 0; border: 1.5px solid var(--rule); background:#fff; border-radius: 4px; cursor:pointer; }
  .labels button.on { background: var(--accent); color:#fff; border-color: var(--accent); }
  .hidden { display:none; }
  .revealed { border-left: 3px solid var(--warn); background: var(--warnbg); }
  .nav button, .top button { font: 14px system-ui, sans-serif; padding: 6px 12px; margin-right: 8px; cursor:pointer; }
  .prog { font: 13px ui-monospace, monospace; color: var(--muted); }
  textarea { width: 100%; box-sizing: border-box; font: 14px system-ui, sans-serif; min-height: 48px; }
</style></head><body><div class="wrap">
<h1 id="title"></h1>
<div class="meta" id="meta"></div>
<div class="top"><button id="prev">← prev</button><button id="next">next →</button><button id="export">export JSONL</button><span class="prog" id="prog"></span></div>
<details class="card"><summary>Rubric (frozen; hash recorded in every label)</summary><pre>__RUBRIC__</pre></details>
<details class="card" id="glossary-card"><summary>Mechanism glossary</summary><div id="glossary"></div></details>
<div id="item"></div>
<script>
const P = __PAYLOAD__;
const HIDDEN_B64 = "__HIDDEN__";
let HIDDEN = null;
function hidden() { if (!HIDDEN) HIDDEN = JSON.parse(decodeURIComponent(escape(atob(HIDDEN_B64)))); return HIDDEN; }
// deterministic shuffle by seed (mulberry32)
function rng(seed){ return function(){ seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; }; }
const order = P.items.map((_,i)=>i); const r = rng(P.seed); for (let i=order.length-1;i>0;i--){ const j=Math.floor(r()*(i+1)); [order[i],order[j]]=[order[j],order[i]]; }
const KEY = "motherlode-grading-" + P.rubric_hash + "-" + P.rater;
let store = {}; try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e) { store = {}; }
function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); } catch(e) {} }
let pos = 0;
document.getElementById("title").textContent = P.title;
document.getElementById("meta").textContent = `rater ${P.rater} · rubric ${P.rubric_hash} · seed ${P.seed} · ${P.items.length} items · labels saved in this browser`;
const g = document.getElementById("glossary"); if (Object.keys(P.glossary).length===0) document.getElementById("glossary-card").classList.add("hidden");
for (const [k,v] of Object.entries(P.glossary)) { const d=document.createElement("div"); d.innerHTML = "<b>"+esc(k)+"</b>: "+esc(v); g.appendChild(d); }
function esc(s){ return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function render(){
  const it = P.items[order[pos]]; const rec = store[it.id] || {};
  const el = document.getElementById("item"); let h = "";
  h += `<div class="card"><p class="k">Item ${pos+1} of ${P.items.length}</p><div class="text">${esc(it.text)}</div></div>`;
  for (const k of P.context_keys) { if (it[k]) h += `<div class="card"><p class="k">${esc(k.replace(/_/g," "))}</p><pre>${esc(it[k])}</pre></div>`; }
  h += `<div class="card"><p class="k">Blind label</p><div class="labels" id="blind">` + P.labels.map(l=>`<button data-l="${esc(l)}" class="${rec.blind===l?"on":""}">${esc(l)}</button>`).join("") + `</div>`;
  h += `<p class="k" style="margin-top:10px">Note</p><textarea id="note">${esc(rec.note||"")}</textarea>`;
  h += `<div style="margin-top:10px"><button id="commit" ${rec.blind?"":"disabled"}>${rec.committed?"committed":"commit blind label"}</button></div></div>`;
  if (rec.committed) {
    const hid = hidden()[it.id] || {};
    h += `<div class="card revealed"><p class="k">Revealed after commit</p>` + P.hidden_keys.map(k=>`<p><b>${esc(k.replace(/_/g," "))}</b>: ${esc(hid[k]||"")}</p>`).join("") ;
    h += `<p class="k" style="margin-top:10px">Revised label (optional, stored separately)</p><div class="labels" id="rev">` + P.labels.map(l=>`<button data-l="${esc(l)}" class="${rec.revealed===l?"on":""}">${esc(l)}</button>`).join("") + `</div></div>`;
  }
  el.innerHTML = h;
  el.querySelectorAll("#blind button").forEach(b=>b.onclick=()=>{ if (rec.committed) return; store[it.id]={...rec, blind:b.dataset.l}; save(); render(); });
  el.querySelectorAll("#rev button").forEach(b=>b.onclick=()=>{ store[it.id]={...(store[it.id]||{}), revealed:b.dataset.l, revealed_ts:new Date().toISOString()}; save(); render(); });
  const note = el.querySelector("#note"); note.oninput = ()=>{ store[it.id]={...(store[it.id]||{}), note:note.value}; save(); };
  const c = el.querySelector("#commit"); if (c) c.onclick = ()=>{ if (!store[it.id]||!store[it.id].blind) return; store[it.id]={...store[it.id], committed:true, blind_ts:new Date().toISOString()}; save(); render(); };
  const done = P.items.filter(x=>store[x.id]&&store[x.id].committed).length;
  document.getElementById("prog").textContent = `${done} committed`;
}
document.getElementById("prev").onclick=()=>{ pos=(pos-1+P.items.length)%P.items.length; render(); };
document.getElementById("next").onclick=()=>{ pos=(pos+1)%P.items.length; render(); };
document.getElementById("export").onclick=()=>{
  const rows=[]; for (const it of P.items){ const rec=store[it.id]; if(!rec||!rec.committed) continue;
    rows.push(JSON.stringify({item_id:it.id, rater:P.rater, label:rec.blind, rubric_hash:P.rubric_hash, pass:"blind", ts:rec.blind_ts, note:rec.note||""}));
    if (rec.revealed) rows.push(JSON.stringify({item_id:it.id, rater:P.rater, label:rec.revealed, rubric_hash:P.rubric_hash, pass:"revealed", ts:rec.revealed_ts}));
  }
  const blob=new Blob([rows.join("\n")+"\n"],{type:"application/jsonl"}); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=`labels-${P.rater}-${P.rubric_hash}.jsonl`; a.click();
};
render();
</script></div></body></html>
"""
