"""Interactive review explorer (LLM vs NRC) — both as a standalone page and as
a reusable embeddable fragment (scoped CSS + body + JS) for the dashboard.

Reads data/takes_merged.json (LLM + NRC sentiment/emotion + star truth).

`build_explorer_parts()` returns {"css","html","js"} that are safe to drop into
any page that defines the --bg/--card/... CSS variables. All selectors are
scoped under `#explorer-root` so they cannot clash with a host page's tables.
"""
from __future__ import annotations
import json, html, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "takes_merged.json")
OUT = os.path.join(ROOT, "data", "explorer.html")

EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]

FRAGMENT_CSS = """
  #explorer-root .controlbar { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:14px; }
  #explorer-root .filters { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; margin-bottom:12px; }
  #explorer-root .chip { padding:6px 14px; border-radius:20px; border:1px solid var(--line); background:var(--card2);
          color:var(--dim); font-size:13px; cursor:pointer; user-select:none; transition:all .12s; }
  #explorer-root .chip:hover { border-color:var(--accent); color:var(--txt); }
  #explorer-root .chip.active { background:var(--accent); color:#062033; font-weight:600; border-color:var(--accent); }
  #explorer-root select { background:var(--card2); color:var(--txt); border:1px solid var(--line); border-radius:8px; padding:6px 8px; font-size:13px; }
  #explorer-root label.flt { font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.5px; margin-right:4px; display:block; }
  #explorer-root .fltgrp { display:flex; flex-direction:column; gap:2px; }
  #explorer-root input[type=search] { background:var(--card2); color:var(--txt); border:1px solid var(--line); border-radius:8px; padding:7px 10px; font-size:13px; min-width:200px; }
  #explorer-root .summary { font-size:13px; color:var(--dim); margin-bottom:12px; }
  #explorer-root .summary b { color:var(--txt); }
  #explorer-root .tablewrap { overflow:auto; border:1px solid var(--line); border-radius:12px; }
  #explorer-root table { border-collapse:collapse; width:100%; min-width:1000px; font-size:13px; }
  #explorer-root th { background:var(--card); color:var(--dim); text-align:left; padding:10px 12px; cursor:pointer;
       white-space:nowrap; border-bottom:1px solid var(--line); font-size:12px; position:sticky; top:0; z-index:2; }
  #explorer-root th:hover { color:var(--txt); } #explorer-root th .arrow { color:var(--accent); }
  #explorer-root td { padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  #explorer-root tbody tr.row { cursor:pointer; } #explorer-root tbody tr.row:hover { background:#24324777; }
  #explorer-root tbody tr.expanded { background:#1e2b46; }
  #explorer-root .star { color:#fbbf24; letter-spacing:1px; white-space:nowrap; }
  #explorer-root .tag { display:inline-block; font-size:11px; padding:2px 8px; border-radius:20px; font-weight:500; white-space:nowrap; }
  #explorer-root .tag.pos { background:#14532d66; color:#86efac; } #explorer-root .tag.neg { background:#7f1d1d66; color:#fca5a5; }
  #explorer-root .tag.llm { outline:1px solid #f472b6; } #explorer-root .tag.nrc { outline:1px solid #38bdf8; }
  #explorer-root .tag.neutral { background:#33415566; color:#cbd5e1; }
  #explorer-root .agree { color:#4ade80; font-weight:600; } #explorer-root .disagree { color:#f87171; font-weight:600; }
  #explorer-root .same { color:#4ade80; } #explorer-root .diff { color:#facc15; }
  #explorer-root .emo { font-size:11px; padding:2px 8px; border-radius:20px; background:#3b0764; }
  #explorer-root .emo2 { font-size:11px; padding:2px 8px; border-radius:20px; background:#164e63; }
  #explorer-root .expandbox { background:var(--card2); border-top:1px solid var(--line); }
  #explorer-root .expandbox .inner { padding:14px 16px 16px; }
  #explorer-root .expandbox .fulltxt { font-size:13px; color:#cbd5e1; margin:8px 0; }
  #explorer-root .expandbox .reason { font-size:12px; color:var(--dim); font-style:italic; }
  #explorer-root .meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  #explorer-root .badge { font-size:11px; padding:2px 8px; border-radius:6px; background:#334155; }
  #explorer-root .badge b { color:var(--txt); }
  #explorer-root .empty { padding:30px; text-align:center; color:var(--dim); font-style:italic; }
  #explorer-root .banner { background:#1e3a5f; border:1px solid #2563eb; color:#93c5fd; padding:8px 12px; border-radius:8px; font-size:12px; margin-bottom:12px; }
  #explorer-root .banner b { color:#dbeafe; }
"""

FRAGMENT_HTML = """<div id="explorer-root">
<div class="banner">The two takes often disagree. Use <b>“Takes &amp; star all agree” / “LLM vs NRC differ”</b> chips to isolate where the LLM and the word-lexicon conflict.<br>
<small>This is expected: NRC tags neutral gift-card words (gift, money, balance) as positive, so it reads most reviews as positive — the LLM is more sensitive to real complaints.</small></div>

<div class="controlbar">
  <div class="filters" id="agree-chips">
    <div class="chip active all" data-agree="all">All reviews</div>
    <div class="chip" data-agree="yes">✓ LLM agrees w/ stars</div>
    <div class="chip" data-agree="no">✗ LLM disagrees w/ stars</div>
    <div class="chip" data-take="plain" style="margin-left:6px">Takes &amp; star all agree</div>
    <div class="chip" data-take="conflict">LLM vs NRC differ</div>
  </div>
  <div class="filters">
    <div class="fltgrp"><label class="flt">LLM sentiment</label>
      <select id="flt-llm-sent"><option value="all">Any</option><option value="positive">Positive</option><option value="negative">Negative</option></select></div>
    <div class="fltgrp"><label class="flt">NRC sentiment</label>
      <select id="flt-nrc-sent"><option value="all">Any</option><option value="positive">Positive</option><option value="negative">Negative</option></select></div>
    <div class="fltgrp"><label class="flt">LLM emotion</label>
      <select id="flt-llm-emo"><option value="all">Any</option>
        <option>anger</option><option>anticipation</option><option>disgust</option><option>fear</option>
        <option>joy</option><option>sadness</option><option>surprise</option><option>trust</option></select></div>
    <div class="fltgrp"><label class="flt">NRC emotion</label>
      <select id="flt-nrc-emo"><option value="all">Any</option>
        <option>anger</option><option>anticipation</option><option>disgust</option><option>fear</option>
        <option>joy</option><option>sadness</option><option>surprise</option><option>trust</option></select></div>
    <div class="fltgrp"><label class="flt">Star rating</label>
      <select id="flt-rating"><option value="all">Any</option><option value="1">1★</option><option value="2">2★</option>
        <option value="3">3★</option><option value="4">4★</option><option value="5">5★</option></select></div>
    <div class="fltgrp"><label class="flt">Search text</label>
      <input type="search" id="flt-search" placeholder="search title or review…"></div>
    <div style="margin-left:auto"><button id="btn-reset" class="chip">Reset</button></div>
  </div>
  <div class="summary">Showing <b id="sum-count">0</b> / <b id="sum-total">0</b> ·
    <span id="sum-takes"></span></div>
</div>

<div class="tablewrap"><table>
  <thead><tr>
    <th data-key="rating_i">★ <span class="arrow"></span></th>
    <th data-key="agree">LLM vs ★ <span class="arrow"></span></th>
    <th data-key="llm_sent">LLM sent <span class="arrow"></span></th>
    <th data-key="llm_emo">LLM emo <span class="arrow"></span></th>
    <th data-key="nrc_sent">NRC sent <span class="arrow"></span></th>
    <th data-key="nrc_emo">NRC emo <span class="arrow"></span></th>
    <th data-key="title">Review <span class="arrow"></span></th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table></div>
</div><!-- /#explorer-root -->"""

FRAGMENT_JS = """<script>
(function(){
const ROWS = __DATA__;
let mode = "all";           // all | yes | no  (agreement with stars)
let takefilter = "any";     // plain | conflict | any
let sortKey = "rating_i", sortAsc = false;
let expandedFp = null;
const $ = s => document.querySelector(s);
// grab elements once, up front
const els = {
  llms: $("#flt-llm-sent"), nrcs: $("#flt-nrc-sent"),
  llme: $("#flt-llm-emo"), nrce: $("#flt-nrc-emo"),
  rating: $("#flt-rating"), search: $("#flt-search"), reset: $("#btn-reset")
};
function get2(){ return { llms: els.llms.value, nrcs: els.nrcs.value,
  llme: els.llme.value, nrce: els.nrce.value,
  rating: els.rating.value === "all" ? null : Number(els.rating.value),
  search: els.search.value.toLowerCase().trim() }; }
function esc(s){ var d=document.createElement("div"); d.textContent=s; return d.innerHTML; }
function matches(r){ var f = get2();
  if (mode==="yes" && !r.agree) return false;
  if (mode==="no" && r.agree) return false;
  if (takefilter==="conflict" && r.llm_sent===r.nrc_sent) return false;
  if (takefilter==="plain" && !(r.llm_sent===r.nrc_sent && r.llm_sent===r.true)) return false;
  if (f.llms!=="all" && r.llm_sent!==f.llms) return false;
  if (f.nrcs!=="all" && r.nrc_sent!==f.nrcs) return false;
  if (f.llme!=="all" && r.llm_emo!==f.llme) return false;
  if (f.nrce!=="all" && r.nrc_emo!==f.nrce) return false;
  if (f.rating!==null && r.rating_i!==f.rating) return false;
  if (f.search){ var hay=((r.title||"")+" "+(r.text||"")).toLowerCase(); if(hay.indexOf(f.search)<0) return false; }
  return true; }
function compare(a,b){ var k=sortKey, av, bv;
  if(k==="title"){ av=(a.title||"").toLowerCase(); bv=(b.title||"").toLowerCase(); }
  else if(k==="agree"){ av=a.agree?1:0; bv=b.agree?1:0; }
  else if(k==="llm_sent"||k==="nrc_sent"){ av=a[k]===b[k]?0:(a[k]<b[k]?-1:1); return sortAsc?av:-av; }
  else { av=a[k]; bv=b[k]; }
  if(av<bv) return sortAsc?-1:1; if(av>bv) return sortAsc?1:-1; return 0; }
function stars(r){ return "\u2605".repeat(r.rating_i)+"\u2606".repeat(5-r.rating_i); }
function sentCls(s){ return s==="positive"?"pos":"neg"; }
function rowHtml(r){
  var vs = r.agree?'<span class="agree">\u2713</span>':'<span class="disagree">\u2717</span>';
  return '<tr class="row'+(expandedFp===r.fp?' expanded':'')+'" data-fp="'+esc(r.fp)+'">'+
    '<td style="cursor:default"><span class="star">'+stars(r)+'</span></td>'+
    '<td>'+vs+'</td>'+
    '<td><span class="tag '+sentCls(r.llm_sent)+' llm">'+r.llm_sent+'</span></td>'+
    '<td><span class="emo">'+esc(r.llm_emo)+'</span></td>'+
    '<td><span class="tag '+sentCls(r.nrc_sent)+' nrc">'+r.nrc_sent+'</span></td>'+
    '<td><span class="emo2">'+esc(r.nrc_emo)+'</span></td>'+
    '<td><b>'+r.title_html+'</b></td></tr>';
}
function nrcScoresHtml(r){
  var sc = r.nrc.scores || {}, keys = Object.keys(sc), parts=[];
  keys.forEach(function(k){ if(sc[k]>0) parts.push('<span class="badge">'+k+' <b>'+sc[k]+'</b></span>'); });
  return parts.length ? parts.join(" ") : '<i>no NRC emotion words found</i>';
}
function expandHtml(r){
  var sentMatch = r.llm_sent===r.nrc_sent?'<span class="same">agree</span>':'<span class="diff">differ</span>';
  return '<tr class="expandbox"><td colspan="7"><div class="inner">'+
    '<div class="meta">'+
      '<span class="badge">Stars <b>'+r.rating_i+'\u2605</b></span>'+
      '<span class="badge">Star-rating truth <b>'+r.true+'</b></span>'+
      '<span class="badge">LLM sentiment <b>'+r.llm_sent+'</b></span>'+
      '<span class="badge">LLM emotion <b>'+esc(r.llm_emo)+'</b></span>'+
      '<span class="badge">NRC sentiment <b>'+r.nrc_sent+'</b></span>'+
      '<span class="badge">NRC emotion <b>'+esc(r.nrc_emo)+'</b></span>'+
      '<span class="badge">Takes '+sentMatch+'</span>'+
    '</div>'+
    '<div class="meta" style="color:#f472b6;font-size:12px;margin-top:8px"><b>LLM reasoning:</b></div>'+
    '<div class="reason">'+(r.reason_html || "(none captured)")+'</div>'+
    '<div class="meta" style="color:#38bdf8;font-size:12px;margin-top:8px"><b>NRC word scores:</b></div>'+
    '<div class="reason">'+nrcScoresHtml(r)+'</div>'+
    '<div class="meta" style="color:var(--accent);font-size:12px;margin-top:8px"><b>Full review text:</b></div>'+
    '<div class="fulltxt">'+r.txt_html+'</div>'+
  '</div></td></tr>';
}
function render(){
  var list = ROWS.filter(matches).sort(compare);
  var takesAgree=0, i;
  for(i=0;i<ROWS.length;i++){ if(ROWS[i].llm_sent===ROWS[i].nrc_sent) takesAgree++; }
  var html="";
  for(i=0;i<list.length;i++){ html+=rowHtml(list[i]); if(expandedFp===list[i].fp) html+=expandHtml(list[i]); }
  $("#tbody").innerHTML = html || '<tr><td colspan="7" class="empty">No reviews match the current filters.</td></tr>';
  var sc=document.getElementById("sum-count"), st=document.getElementById("sum-total"), sa=document.getElementById("sum-takes");
  if(sc) sc.textContent = list.length;
  if(st) st.textContent = ROWS.length;
  if(sa) sa.textContent = 'takes agree: '+takesAgree+' ('+Math.round(takesAgree/ROWS.length*100)+'%) \u00b7 takes differ: '+(ROWS.length-takesAgree);
  document.querySelectorAll("#agree-chips .chip").forEach(function(c){
    var on = c.dataset.agree ? c.dataset.agree===mode : c.dataset.take===takefilter;
    if(on) c.classList.add("active"); else c.classList.remove("active");
  });
}
// events
document.querySelectorAll("#agree-chips .chip").forEach(function(c){
  c.addEventListener("click", function(){
    if(c.dataset.agree){ mode=c.dataset.agree; takefilter="any"; }
    else { takefilter=c.dataset.take; mode="all"; }
    render();
  });
});
["llms","nrcs","llme","nrce","rating"].forEach(function(k){ els[k].addEventListener("change", render); });
els.search.addEventListener("input", render);
els.reset.addEventListener("click", function(){
  mode="all"; takefilter="any"; expandedFp=null;
  ["llms","nrcs","llme","nrce","rating"].forEach(function(k){ els[k].value="all"; });
  els.search.value=""; render();
});
document.querySelectorAll("#explorer-root th").forEach(function(th){
  th.addEventListener("click", function(){
    var k=th.dataset.key; if(!k) return;
    if(sortKey===k) sortAsc=!sortAsc; else { sortKey=k; sortAsc=true; }
    document.querySelectorAll("#explorer-root th .arrow").forEach(function(a){ a.textContent=""; });
    th.querySelector(".arrow").textContent = sortAsc?"\u25B2":"\u25BC"; render();
  });
});
$("#tbody").addEventListener("click", function(e){
  var tr = e.target && e.target.closest ? e.target.closest("tr.row") : null;
  if(!tr) return;
  var fp = tr.dataset.fp;
  expandedFp = (expandedFp===fp)?null:fp; render();
});
render();
})();
</script>"""


def esc(s):
    return html.escape(str(s))


def build_explorer_parts(src: str = SRC) -> dict:
    """Return {"css","html","js"} for embedding the explorer in a host page."""
    data = json.load(open(src))
    rows = data["rows"]
    for r in rows:
        r["agree"] = r["llm"]["sentiment"] == r["true"]
        r["rating_i"] = int(r["rating"])
        r["txt_html"] = esc(r["text"] or "(no text)")
        r["title_html"] = esc(r["title"] or "(no title)")
        r["reason_html"] = esc(r["llm"].get("reason", ""))
        r["llm_sent"] = r["llm"]["sentiment"]
        r["llm_emo"] = r["llm"]["emotion"]
        r["nrc_sent"] = r["nrc"]["sentiment"]
        r["nrc_emo"] = r["nrc"]["emotion"]
    data_json = json.dumps(rows, ensure_ascii=False)
    js = FRAGMENT_JS.replace("__DATA__", data_json)
    return {"css": FRAGMENT_CSS, "html": FRAGMENT_HTML, "js": js}


def main() -> None:
    p = build_explorer_parts(SRC)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review Explorer (LLM vs NRC) — Gift Card Classifier</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --card2:#243247; --line:#334155;
           --txt:#e2e8f0; --dim:#94a3b8; --accent:#38bdf8;
           --pos:#16a34a; --neg:#dc2626; --posbg:#14532d29; --negbg:#7f1d1d29; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:var(--txt); line-height:1.45; }}
  .wrap {{ max-width:1280px; margin:0 auto; padding:24px 20px 70px; }}
  h1 {{ font-size:20px; margin:0 0 2px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:20px; }}
  {p["css"]}
</style></head><body><div class="wrap">
<h1>Review Explorer — LLM vs NRC</h1>
<div class="sub">Every review has both independent takes: <b>LLM</b> (prompt, pink outline) and <b>NRC Emotion Lexicon</b> (rule-based word scores, blue outline), plus star-rating ground truth.</div>
{p["html"]}
</div>
{p["js"]}
</body></html>"""
    with open(OUT, "w") as f:
        f.write(doc)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
