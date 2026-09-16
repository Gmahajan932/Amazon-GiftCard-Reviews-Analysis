"""Generate a self-contained HTML dashboard from classifier results.

Reads data/classifications.results_120.json and produces dashboard.html with
inline SVG charts (no external CDN), so it renders anywhere, offline.
"""
from __future__ import annotations
import json, html, os
from collections import Counter
from make_explorer import build_explorer_parts

ROOT = "/Users/gaurimahajan/git-and-github-lab"
SRC = os.path.join(ROOT, "data/classifications_3way.results_120.json")
OUT = os.path.join(ROOT, "data", "dashboard.html")

# Build the LLM-vs-NRC explorer fragment (scoped CSS/body/JS) to embed as a tab.
EXPLORER = build_explorer_parts()

# Agreement analysis for the explorer tab (same source the explorer embeds).
with open(os.path.join(ROOT, "data/takes_merged.json")) as _f:
    _takes = json.load(_f)["rows"]
TAKES_N = len(_takes)
TAKES_AGREE = sum(1 for r in _takes if r["llm"]["sentiment"] == r["nrc"]["sentiment"])
TAKES_DIFFER = TAKES_N - TAKES_AGREE
TAKES_EMO_AGREE = sum(1 for r in _takes if r["llm"]["emotion"] == r["nrc"]["emotion"])
TAKES_LLM_VS_STAR = sum(1 for r in _takes if r["llm"]["sentiment"] == r["true"])
TAKES_NRC_VS_STAR = sum(1 for r in _takes if r["nrc"]["sentiment"] == r["true"])


def metrics(rows):
    tp = tn = fp = fn = 0
    for r in rows:
        p, t = r["classification"], r["true"]
        if p == t:
            if p == "positive":
                tp += 1
            else:
                tn += 1
        else:
            if p == "positive":
                fp += 1
            else:
                fn += 1
    n = len(rows)
    acc = (tp + tn) / max(1, n)
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    return {"n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "acc": acc, "prec": prec, "rec": rec, "f1": f1}


def esc(s):
    return html.escape(str(s))


rows = json.load(open(SRC))
m = metrics(rows)

CLASSES = ["positive", "neutral", "negative"]
# recompute confusion as a dict of dicts {true: {pred:n}} for the 3-way view
conf3 = {t: {p: 0 for p in ["positive", "neutral", "negative"]} for t in ["positive", "neutral", "negative"]}
for r in rows:
    conf3[r["true"]][r["classification"]] = conf3[r["true"]].get(r["classification"], 0) + 1
correct3 = sum(conf3[c][c] for c in CLASSES)
n3 = len(rows)
acc3 = correct3 / max(1, n3)
# per-class f1
def f1of(tp, fp, fn):
    p = tp / max(1, tp + fp); r = tp / max(1, tp + fn)
    return 2 * p * r / max(1e-9, p + r)
per_class3 = {}
for c in CLASSES:
    tp = conf3[c][c]; fp = sum(conf3[t][c] for t in CLASSES if t != c); fn = sum(conf3[c][p] for p in CLASSES if p != c)
    per_class3[c] = {"n": sum(conf3[c].values()), "tp": tp, "fp": fp, "fn": fn,
                     "prec": tp / max(1, tp + fp), "rec": tp / max(1, tp + fn),
                     "f1": f1of(tp, fp, fn)}
macro_f1_3 = sum(per_class3[c]["f1"] for c in CLASSES) / 3

# compact per-review fields for the descriptive comparison table
cmp_rows = []
for r in sorted(rows, key=lambda x: (x["true"], x["rating"])):
    cmp_rows.append({
        "title": (r["title"] or "(no title)"),
        "text": (r["text"] or "(no text)")[:240],
        "true": r["true"],
        "pred": r["classification"],
        "rating": r["rating"],
        "conf": round(float(r.get("confidence", 0) or 0), 2),
        "tone": r.get("tone", ""),
        "len": r.get("length", ""),
        "ok": r["classification"] == r["true"],
    })
CMP_JSON = json.dumps(cmp_rows, ensure_ascii=False)

# Client-side script for the descriptive comparison table (plain string, not f-string,
# so the JS {…} template literals don't collide with Python's f-string braces).
CMP_SCRIPT = r"""<script>
const CMP = __CMP_JSON__;
let cmpClass = "all", cmpShow = "all";

function cmpRows(){
  return CMP.filter(function(r){
    if (cmpClass!=="all" && r.true!==cmpClass) return false;
    if (cmpShow==="right" && !r.ok) return false;
    if (cmpShow==="wrong" && r.ok) return false;
    return true;
  });
}

function clsOf(s){ return s==="positive" ? "pos" : (s==="neutral" ? "neutral" : "neg"); }
function cmpCell(r){
  var truth = '<span class="cmplabel ' + clsOf(r.true) + '">' + r.true + '</span>';
  var pred  = '<span class="cmplabel ' + clsOf(r.pred) + '">' + r.pred + '</span>';
  var mark  = r.ok ? '<span class="ok-mark">' + '\u2713 right</span>' : '<span class="x-mark">' + '\u2717 wrong</span>';
  var predCell = r.ok ? pred : '<span style="text-decoration:line-through;opacity:.6">' + pred + '</span>';
  return '<tr class="' + (r.ok?'':'wrong') + '">' +
    '<td>' + r.rating + '\u2605</td>' +
    '<td>' + truth + '</td>' +
    '<td>' + predCell + ' \u2192 ' + mark + '</td>' +
    '<td>' + esc(r.title) + '</td>' +
    '<td>' + esc(r.text) + '</td>' +
    '<td class="dim">' + r.conf.toFixed(2) + '</td>' +
    '<td class="dim">' + r.tone + ' / ' + r.len + '</td></tr>';
}

function renderCmp(){
  var list = cmpRows();
  var byClass = { positive: [], neutral: [], negative: [] };
  list.forEach(function(r){ byClass[r.true] = byClass[r.true] || []; byClass[r.true].push(r); });
  var html = '<tr><th>Stars</th><th>Correct answer</th><th>Model predicted</th>' +
             '<th>Title</th><th>Review text</th><th>Conf.</th><th>Tone / len</th></tr>';
  Object.keys(byClass).forEach(function(cls){
    var sub = byClass[cls];
    if (!sub.length) return;
    var right = sub.filter(function(r){return r.ok;}).length;
    var wrong = sub.length - right;
    html += '<tr class="cmp-classhead"><td colspan="7">' +
      (cls==="positive" ? 'POSITIVE class' : (cls==="neutral" ? 'NEUTRAL class' : 'NEGATIVE class')) +
      ' <span class="dim" style="font-weight:400">\u2014 ' + sub.length + ' reviews, ' +
      right + ' \u2713 \u00b7 ' + wrong + ' \u2717</span></td></tr>';
    sub.forEach(function(r){ html += cmpCell(r); });
  });
  document.getElementById("cmp-body").innerHTML = html +
    (list.length ? "" : '<tr><td colspan="7" class="dim">No reviews match.</td></tr>');
  document.getElementById("cmp-count").textContent = list.length;
  var all = CMP.length, right = CMP.filter(function(r){return r.ok;}).length;
  document.getElementById("cmp-stats").textContent =
    'right: ' + right + ' (' + (right/all*100).toFixed(0) + '%) \u00b7 wrong: ' + (all-right) +
    ' (' + ((all-right)/all*100).toFixed(0) + '%) \u2014 model total: ' + right + '/' + all;
  document.querySelectorAll(".cmp-chip").forEach(function(c){
    var k = c.dataset.class !== undefined ? "class" : "show";
    var active = (k==="class") ? c.dataset.class===cmpClass : c.dataset.show===cmpShow;
    if (active) c.classList.add("active"); else c.classList.remove("active");
  });
}
function esc(s){ var d=document.createElement("div"); d.textContent=s; return d.innerHTML; }
document.querySelectorAll(".cmp-chip").forEach(function(c){
  c.addEventListener("click", function(){
    if (c.dataset.class !== undefined) cmpClass = c.dataset.class;
    else cmpShow = c.dataset.show;
    renderCmp();
  });
});
renderCmp();

// tab switching
document.querySelectorAll(".tab").forEach(function(t){
  t.addEventListener("click", function(){
    document.querySelectorAll(".tab").forEach(function(x){ x.classList.remove("active"); });
    document.querySelectorAll(".tabbody").forEach(function(b){ b.classList.remove("active"); });
    t.classList.add("active");
    document.getElementById("tab-" + t.dataset.tab).classList.add("active");
  });
});
</script>"""

# --- breakdown helpers ---
def pct(a, b):
    return 100.0 * a / b if b else 0.0

def bar_seg(frac, color, label):
    return f'<div class="seg" style="width:{frac*100:.1f}%;background:{color}" title="{label}"></div>'

# per-rating correct/wrong
ratings = sorted({r["rating"] for r in rows})
rating_rows = []
for rt in ratings:
    sub = [r for r in rows if r["rating"] == rt]
    corr = sum(1 for r in sub if r["classification"] == r["true"])
    rating_rows.append({"rating": rt, "n": len(sub), "corr": corr,
                        "acc": corr / len(sub)})

# per length bucket
len_rows = []
for L in ["short", "medium", "long"]:
    sub = [r for r in rows if r["length"] == L]
    if not sub:
        continue
    corr = sum(1 for r in sub if r["classification"] == r["true"])
    len_rows.append({"len": L, "n": len(sub), "corr": corr, "acc": corr / len(sub)})

# per tone
tone_rows = []
for T in ["positive", "negative", "neutral", "mixed"]:
    sub = [r for r in rows if r["tone"] == T]
    if not sub:
        continue
    corr = sum(1 for r in sub if r["classification"] == r["true"])
    tone_rows.append({"tone": T, "n": len(sub), "corr": corr, "acc": corr / len(sub)})

# confidence buckets (low <0.6, mid 0.6-0.8, high >0.8)
conf_buckets = Counter()
for r in rows:
    c = r["confidence"]
    if c < 0.6: conf_buckets["low (<0.6)"] += 1
    elif c <= 0.8: conf_buckets["mid (0.6–0.8)"] += 1
    else: conf_buckets["high (>0.8)"] += 1

# correctness by confidence
low_corr = sum(1 for r in rows if r["confidence"] < 0.6 and r["classification"] == r["true"])
mid_corr = sum(1 for r in rows if 0.6 <= r["confidence"] <= 0.8 and r["classification"] == r["true"])
high_corr = sum(1 for r in rows if r["confidence"] > 0.8 and r["classification"] == r["true"])
low_n = sum(1 for r in rows if r["confidence"] < 0.6)
mid_n = sum(1 for r in rows if 0.6 <= r["confidence"] <= 0.8)
high_n = sum(1 for r in rows if r["confidence"] > 0.8)

# prediction mix
pred_pos = sum(1 for r in rows if r["classification"] == "positive")
pred_neu = sum(1 for r in rows if r["classification"] == "neutral")
pred_neg = sum(1 for r in rows if r["classification"] == "negative")

# wrong examples
wrong = [r for r in rows if r["classification"] != r["true"]]
correct = [r for r in rows if r["classification"] == r["true"]]
conf_samples = sorted(rows, key=lambda r: r["confidence"], reverse=True)

# ---------- build HTML ----------
def rating_acc_bars():
    out = []
    for r in rating_rows:
        out.append(f'''
        <div class="barr"><div class="barlbl">rating <b>{r["rating"]}★</b>
          <span class="dim">({r["n"]} rev)</span></div>
          <div class="bar"><div class="barfill" style="width:{r['acc']*100:.0f}%"></div></div>
          <div class="barval">{r['acc']*100:.0f}%</div></div>''')
    return "\n".join(out)

def len_bars():
    out = []
    for r in len_rows:
        out.append(f'''
        <div class="barr"><div class="barlbl"><b>{r["len"]}</b>
          <span class="dim">({r["n"]} rev)</span></div>
          <div class="bar"><div class="barfill" style="width:{r['acc']*100:.0f}%"></div></div>
          <div class="barval">{r['acc']*100:.0f}%</div></div>''')
    return "\n".join(out)

def tone_bars():
    out = []
    for r in tone_rows:
        out.append(f'''
        <div class="barr"><div class="barlbl"><b>{r["tone"]}</b>
          <span class="dim">({r["n"]} rev)</span></div>
          <div class="bar"><div class="barfill" style="width:{r['acc']*100:.0f}%"></div></div>
          <div class="barval">{r['acc']*100:.0f}%</div></div>''')
    return "\n".join(out)

def conf_bars():
    items = [("low (<0.6)", low_n, low_corr), ("mid (0.6–0.8)", mid_n, mid_corr),
             ("high (>0.8)", high_n, high_corr)]
    out = []
    for lbl, n_, corr_ in items:
        out.append(f'''
        <div class="barr"><div class="barlbl"><b>{lbl}</b>
          <span class="dim">({n_} rev)</span></div>
          <div class="bar"><div class="barfill" style="width:{pct(corr_, n_):.0f}%"></div></div>
          <div class="barval">{pct(corr_, n_):.0f}% acc</div></div>''')
    return "\n".join(out)

# stacked distribution bars (tone & length mix)
def tone_dist():
    counts = Counter(r["tone"] for r in rows)
    total = len(rows)
    colors = {"positive": "#16a34a", "negative": "#dc2626", "neutral": "#64748b", "mixed": "#d97706", "unknown": "#94a3b8"}
    segs = "".join(bar_seg(counts[c]/total, colors.get(c,"#94a3b8"), f"{c} {counts[c]}") for c in counts)
    return f'<div class="bar stacked">{segs}</div>', counts, colors

def len_dist():
    counts = Counter(r["length"] for r in rows)
    total = len(rows)
    colors = {"short": "#2563eb", "medium": "#7c3aed", "long": "#0891b2", "unknown": "#94a3b8"}
    segs = "".join(bar_seg(counts[c]/total, colors.get(c,"#94a3b8"), f"{c} {counts[c]}") for c in counts)
    return f'<div class="bar stacked">{segs}</div>', counts, colors

tone_dist_html, tone_counts, tone_colors = tone_dist()
len_dist_html, len_counts, len_colors = len_dist()

def legend_html(counts, colors):
    out = []
    for k, v in counts.items():
        out.append(f'<span class="lg"><i style="background:{colors[k]}"></i>{k} <b>{v}</b> ({pct(v,len(rows)):.0f}%)</span>')
    return " ".join(out)

def review_cards(items, label):
    out = [f'<h3>{label} <span class="dim">({len(items)})</span></h3>']
    cards = []
    for r in items[:8]:
        ok = r["classification"] == r["true"]
        chips = f'''<span class="chip {r['classification']}">{r['classification']}</span>
                    <span class="chip truth">true: {r['true']}</span>
                    <span class="chip tone">tone: {r['tone']}</span>
                    <span class="chip len">len: {r['length']}</span>
                    <span class="chip conf">conf: {r['confidence']:.2f}</span>
                    <span class="chip star">rating: {r['rating']}★</span>'''
        cards.append(f'''
        <div class="card {'mismatch' if not ok else ''}">
          <div class="chips">{chips}</div>
          <div class="ctitle">{esc(r['title']) or '(no title)'}</div>
          <div class="ctext">{esc(r['text'][:220])}{'…' if len(r['text'])>220 else ''}</div>
          <div class="creason"><b>model:</b> {esc(r.get('reason',''))}</div>
        </div>''')
    out.append('<div class="cards">' + "".join(cards) + '</div>')
    return "\n".join(out)

def donut(frac, color, labeltxt, sub):
    # inline SVG donut — percentage centered inside a fixed ring, caption below
    r = 28; c = 2 * 3.14159 * r
    dash = frac * c
    return f'''
    <div class="donutwrap">
      <div class="donutring">
        <svg viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="12"/>
          <circle cx="40" cy="40" r="{r}" fill="none" stroke="{color}" stroke-width="12"
              stroke-dasharray="{dash:.1f} {c:.1f}" stroke-linecap="round"
              transform="rotate(-90 40 40)"/>
        </svg>
        <div class="donutpct">{frac*100:.0f}%</div>
      </div>
      <div class="donuttxt">{labeltxt}</div>
      <div class="donutsub dim">{sub}</div>
    </div>'''

html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gift Card Review Classifier — Results Dashboard</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --card2:#243247; --line:#334155;
           --txt:#e2e8f0; --dim:#94a3b8; --pos:#16a34a; --neg:#dc2626; --acc:#38bdf8; --accent:#38bdf8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:var(--txt); line-height:1.45; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  h2 {{ font-size:16px; color:var(--acc); margin:30px 0 12px; border-bottom:1px solid var(--line); padding-bottom:8px; letter-spacing:.3px;}}
  h3 {{ font-size:14px; margin:4px 0 10px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:24px; }}
  .dim {{ color:var(--dim); font-weight:normal; font-size:12px; }}
  .grid {{ display:grid; gap:14px; }}
  .g4 {{ grid-template-columns:repeat(4,1fr); }}
  .g2 {{ grid-template-columns:repeat(2,1fr); }}
  .card, .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .kpi {{ text-align:center; padding:18px 12px; }}
  .kpi .val {{ font-size:30px; font-weight:700; color:var(--acc); }}
  .kpi .lab {{ color:var(--dim); font-size:12px; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }}
  .kpi.warn .val {{ color:var(--pos); }}
  .kpi.red .val {{ color:var(--neg); }}
  @media(max-width:720px) {{ .g4 {{ grid-template-columns:repeat(2,1fr);}} .g2 {{ grid-template-columns:1fr;}} }}
  .barr {{ display:grid; grid-template-columns:150px 1fr 46px; gap:10px; align-items:center; margin:8px 0; }}
  .barlbl {{ font-size:13px; text-align:right; }}
  .bar {{ height:20px; background:#334155; border-radius:6px; overflow:hidden; }}
  .bar.stacked {{ display:flex; height:26px; }}
  .seg {{ height:100%; }}
  .barfill {{ height:100%; background:linear-gradient(90deg,#38bdf8,#0284c7); border-radius:6px; }}
  .barval {{ font-size:12px; color:var(--dim); }}
  .lg {{ display:inline-flex; align-items:center; gap:6px; margin:6px 12px 6px 0; font-size:12px; color:var(--dim); }}
  .lg i {{ width:10px; height:10px; border-radius:3px; display:inline-block; }}
  .donuts {{ display:flex; gap:16px; flex-wrap:wrap; align-items:flex-start; }}
  .donutwrap {{ text-align:center; background:var(--card2); padding:12px 12px 10px; border-radius:10px; width:150px; }}
  .donutwrap .donutring {{ position:relative; width:84px; height:84px; margin:0 auto; }}
  .donutwrap svg {{ display:block; width:100%; height:100%; }}
  .donutwrap .donutpct {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
                         font-size:15px; font-weight:700; }}
  .donuttxt {{ font-size:12px; margin-top:8px; font-weight:600; }}
  .donutsub {{ font-size:11px; }}
  .cards {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
  @media(max-width:720px) {{ .cards {{ grid-template-columns:1fr;}} }}
  .card.mismatch {{ border-color:var(--neg); background:#2b1a20; }}
  .chips {{ margin-bottom:6px; display:flex; flex-wrap:wrap; gap:4px; }}
  .chip {{ font-size:10px; padding:2px 7px; border-radius:20px; background:#334155; color:var(--txt); }}
  .chip.positive {{ background:#14532d; }}
  .chip.negative {{ background:#7f1d1d; }}
  .chip.truth {{ background:#1e3a8a; }}
  .chip.tone {{ background:#3b0764; }}
  .chip.len {{ background:#164e63; }}
  .chip.conf {{ background:#3f3f46; }}
  .chip.star {{ background:#78350f; }}
  .ctitle {{ font-weight:600; font-size:13px; margin-bottom:3px; }}
  .ctext {{ font-size:12px; color:#cbd5e1; }}
  .creason {{ font-size:11px; color:var(--dim); margin-top:6px; font-style:italic; }}
  .cm {{ display:grid; grid-template-columns:auto auto auto; gap:8px; }}
  .cmcell {{ padding:14px; text-align:center; border-radius:10px; font-size:20px; font-weight:700; }}
  .cmhead {{ font-size:12px; color:var(--dim); font-weight:600; display:flex; align-items:center; justify-content:center;}}
  .cm label {{ color:var(--dim); font-size:11px; display:block; margin-top:2px; font-weight:400; }}
  .cm-main {{ background:#1e3a8a; }}
  .cm-off {{ background:#7f1d1d; }}
  .cm-neu {{ background:#78350f; }}
  .cm3 {{ display:grid; grid-template-columns:auto repeat(3,1fr); gap:8px; }}
  .cm3 .cmcell {{ padding:14px; text-align:center; border-radius:10px; font-size:18px; font-weight:700; }}
  /* ---- descriptive comparison table ---- */
  .cmp-controls {{ display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; margin-bottom:14px; }}
  .cmp-chips {{ display:flex; flex-wrap:wrap; gap:8px; }}
  .cmp-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  .cmp-table th {{ text-align:left; padding:10px 12px; background:var(--card); color:var(--dim);
                   font-size:12px; border-bottom:1px solid var(--line); position:sticky; top:0; }}
  .cmp-table td {{ padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
  .cmp-table tr.wrong td {{ background:#2b1a20aa; }}
  .cmp-table tr.wrong td:first-child {{ box-shadow:inset 3px 0 0 var(--neg); }}
  .cmp-classhead td {{ background:var(--card); color:var(--acc); font-weight:700; font-size:13px;
                       border-bottom:2px solid var(--acc); }}
  .cmplabel {{ display:inline-block; font-size:11px; padding:2px 9px; border-radius:20px; font-weight:600; }}
  .cmplabel.pos {{ background:#14532d; color:#86efac; }}
  .cmplabel.neg {{ background:#7f1d1d; color:#fca5a5; }}
  .cmplabel.neutral {{ background:#78350f; color:#fde047; }}
  .cmplabel.plain {{ background:#334155; color:var(--txt); }}
  .ok-mark {{ color:var(--pos); font-weight:700; }} .x-mark {{ color:var(--neg); font-weight:700; }}
  /* ---- tabs ---- */
  .tabs {{ display:flex; gap:6px; flex-wrap:wrap; margin:18px 0 22px; border-bottom:1px solid var(--line); padding-bottom:0; }}
  .tab {{ background:var(--card); border:1px solid var(--line); color:var(--dim); padding:10px 20px;
         border-radius:10px 10px 0 0; cursor:pointer; font-size:13px; margin-bottom:-1px; user-select:none; transition:all .12s; }}
  .tab:hover {{ color:var(--txt); border-color:var(--line2); }}
  .tab.active {{ background:var(--card); color:var(--acc); font-weight:600; border-color:var(--line2);
                 border-bottom-color:var(--card); }}
  .tabbody {{ display:none; }}
  .tabbody.active {{ display:block; }}
  {EXPLORER['css']}
</style>
</head>
<body>
<div class="wrap">

  <h1>Amazon Gift-Card Review Classifier</h1>
  <div class="sub">LLM (DeepSeek via prompting) · tone-primary, length-tiebreaker · 3-class (positive/neutral/negative) · stratified sample vs. star-rating proxy</div>

  <div class="tabs">
    <button class="tab active" data-tab="overview">📊 Overview</button>
    <button class="tab" data-tab="descriptive">🔎 Reviews vs Model Predictions</button>
    <button class="tab" data-tab="confusion">🔀 Confusion &amp; Tone</button>
    <button class="tab" data-tab="explorer">🔎 LLM vs NRC Explorer</button>
    <button class="tab" data-tab="errors">❌ Where it went wrong</button>
  </div>

  <div class="tabbody active" id="tab-overview">
  <div class="grid g4">
    <div class="kpi"><div class="val">{acc3*100:.1f}%</div><div class="lab">Overall accuracy</div></div>
    <div class="kpi"><div class="val">{macro_f1_3*100:.1f}%</div><div class="lab">Macro F1 (3-class)</div></div>
    <div class="kpi"><div class="val">{per_class3['positive']['f1']*100:.1f}%</div><div class="lab">F1 positive</div></div>
    <div class="kpi"><div class="val" style="color:#facc15">{per_class3['neutral']['f1']*100:.1f}%</div><div class="lab">F1 neutral</div></div>
  </div>
  <div class="grid g4" style="margin-top:14px">
    <div class="kpi"><div class="val">{per_class3['negative']['f1']*100:.1f}%</div><div class="lab">F1 negative</div></div>
    <div class="kpi"><div class="val">{per_class3['positive']['prec']*100:.1f}%</div><div class="lab">Precision (pos)</div></div>
    <div class="kpi"><div class="val">{per_class3['positive']['rec']*100:.1f}%</div><div class="lab">Recall (pos)</div></div>
    <div class="kpi"><div class="val">{n3}</div><div class="lab">Reviews</div></div>
  </div>

  <div class="grid g2" style="margin-top:14px">
    <div class="card">
      <h3>Prediction mix</h3>
      <div class="donuts">{donut(pred_pos/m['n'], '#16a34a', f"Positive {pred_pos}", f"{pct(pred_pos,m['n']):.0f}% of predictions")}{donut(pred_neu/m['n'], '#facc15', f"Neutral {pred_neu}", f"{pct(pred_neu,m['n']):.0f}% of predictions")}{donut(pred_neg/m['n'], '#dc2626', f"Negative {pred_neg}", f"{pct(pred_neg,m['n']):.0f}% of predictions")}</div>
    </div>
    <div class="card">
      <h3>Accuracy by review length</h3>
      {len_bars()}
    </div>
  </div>

  <h3>Accuracy by star rating</h3>
  <div class="card">{rating_acc_bars()}</div>

  <h3>Confidence</h3>
  <div class="card">
    <div style="margin-bottom:14px">{conf_bars()}</div>
    <div class="dim">Model self-reported confidence vs. correctness. Low-confidence predictions are where ambiguity lives — many are exactly the "words say one thing, stars say another" cases.</div>
  </div>
  </div><!-- /tab-overview -->

  <div class="tabbody" id="tab-confusion">
  <h3>Confusion Matrix <span class="dim">(vs star-rating ground truth)</span></h3>
  <div class="card">
    <div class="cm3">
      <div class="cmcell cmhead">Predicted →<br>Actual ↓</div>
      <div class="cmcell cmhead">Positive</div><div class="cmcell cmhead">Neutral</div><div class="cmcell cmhead">Negative</div>
      <div class="cmcell cmhead">Positive</div>
      <div class="cmcell cm-main">{conf3['positive']['positive']}</div>
      <div class="cmcell cm-off">{conf3['positive']['neutral']}</div>
      <div class="cmcell cm-off">{conf3['positive']['negative']}</div>
      <div class="cmcell cmhead">Neutral</div>
      <div class="cmcell cm-off">{conf3['neutral']['positive']}</div>
      <div class="cmcell cm-neu">{conf3['neutral']['neutral']}</div>
      <div class="cmcell cm-off">{conf3['neutral']['negative']}</div>
      <div class="cmcell cmhead">Negative</div>
      <div class="cmcell cm-off">{conf3['negative']['positive']}</div>
      <div class="cmcell cm-off">{conf3['negative']['neutral']}</div>
      <div class="cmcell cm-main">{conf3['negative']['negative']}</div>
    </div>
    <div class="dim" style="margin-top:10px">n={n3} · perfect predictions lie on the diagonal · star-rating proxy: 4–5★ = positive · 3★ = neutral · 1–2★ = negative</div>
  </div>

  <h3>Where length &amp; tone shaped the answer</h3>
  <div class="grid g2">
    <div class="card">
      <h3>Length use ({m['n']} reviews)</h3>
      {len_dist_html}
      <div style="margin-top:10px">{legend_html(len_counts, len_colors)}</div>
    </div>
    <div class="card">
      <h3>Tone detected</h3>
      {tone_dist_html}
      <div style="margin-top:10px">{legend_html(tone_counts, tone_colors)}</div>
    </div>
  </div>
  <div style="margin-top:12px"></div>
  <div class="card">
    <h3>Accuracy by model-reported tone</h3>
    {tone_bars()}
  </div>
  </div><!-- /tab-confusion -->

  <div class="tabbody" id="tab-descriptive">
  <h3>Reviews vs Model Predictions <span class="dim">(correct answer vs. prediction, by class)</span></h3>
  <div class="card">
    <p class="dim" style="margin:0 0 12px">
      Every review, grouped by its <b>true</b> class (from the star-rating). Green rows = the model got it right;
      <span style="color:var(--neg)"><b>red</b> rows = wrong</span> — the <b>correct answer</b> vs. what the
      <b>model predicted</b>, side by side. Filter to see only where we went wrong.</p>
    <div class="cmp-controls">
      <div class="cmp-chips">
        <button class="chip cmp-chip active" data-class="all">All classes</button>
        <button class="chip cmp-chip" data-class="positive">Positive class</button>
        <button class="chip cmp-chip" data-class="neutral">Neutral class</button>
        <button class="chip cmp-chip" data-class="negative">Negative class</button>
      </div>
      <div class="cmp-chips" style="margin-left:auto">
        <button class="chip cmp-chip active" data-show="all">All</button>
        <button class="chip cmp-chip" data-show="right">✓ Correct only</button>
        <button class="chip cmp-chip" data-show="wrong">✗ Wrong only</button>
      </div>
    </div>
    <div class="summary" style="margin-bottom:10px">Showing <b id="cmp-count">0</b> reviews ·
      <span id="cmp-stats"></span></div>
    <div style="overflow:auto"><table class="cmp-table" id="cmp-body"></table></div>
  </div>
  </div><!-- /tab-descriptive -->

  <div class="tabbody" id="tab-errors">
  <h3>Where it went wrong</h3>
  <div class="card" style="margin-bottom:14px">
    <p class="dim" style="margin:0 0 4px;font-size:13px;line-height:1.6">
      This tab shows the <b>individual reviews</b> behind the headline metrics. Two groups of cards:
    </p>
    <p class="dim" style="margin:0 0 12px;font-size:13px;line-height:1.6">
      <b style="color:var(--neg)">⚠ Mismatches</b> — the {len(wrong)} reviews where the model's label does
      <b>not</b> match the star-rating ground truth. These are where it "went wrong" against the proxy.
      Read the model's <i>reason</i> on each card to see <i>why</i> — most are the classic case where the words
      and the stars disagree (e.g. a 3★ review whose tone is neutral/positive).<br>
      <b style="color:var(--acc)">🎯 Highest-confidence</b> — the model's most certain predictions, so you can
      sanity-check what it's most sure about and confirm they line up with the stars.<br>
      <span class="dim" style="font-size:12px">Cards are reduced to the first 8 of each group — the full dataset is
      filterable in the <b>Reviews vs Model Predictions</b> and <b>LLM vs NRC Explorer</b> tabs.</span>
    </p>
  </div>
  {review_cards(wrong, '⚠ Mismatches vs. star-rating (where words & stars disagree)')}
  {review_cards(conf_samples[:6], '🎯 Highest-confidence predictions')}
  </div><!-- /tab-errors -->

  <div class="tabbody" id="tab-explorer">
  <h3>Review Explorer — LLM vs NRC <span class="dim">(independent takes on every review)</span></h3>

  <div class="card" style="margin-bottom:14px">
    <h3>How often do the two takes agree?</h3>
    <div class="grid g4">
      <div class="kpi"><div class="val">{TAKES_N}</div><div class="lab">Reviews</div></div>
      <div class="kpi"><div class="val">{TAKES_AGREE} <span style="font-size:14px;color:var(--dim)">({(TAKES_AGREE/TAKES_N*100):.0f}%)</span></div><div class="lab">LLM &amp; NRC agree</div></div>
      <div class="kpi" style="border-color:var(--neg)"><div class="val">{TAKES_DIFFER} <span style="font-size:14px;color:var(--dim)">({(TAKES_DIFFER/TAKES_N*100):.0f}%)</span></div><div class="lab">LLM &amp; NRC differ</div></div>
      <div class="kpi"><div class="val">{TAKES_EMO_AGREE} <span style="font-size:14px;color:var(--dim)">({(TAKES_EMO_AGREE/TAKES_N*100):.0f}%)</span></div><div class="lab">Emotion agree</div></div>
    </div>
    <div class="bar" style="height:16px;display:flex;margin:14px 0 6px;overflow:hidden;border-radius:6px">
      <div style="width:{(TAKES_AGREE/TAKES_N*100):.1f}%;background:var(--pos)" title="Agree {TAKES_AGREE}"></div>
      <div style="width:{(TAKES_DIFFER/TAKES_N*100):.1f}%;background:var(--neg)" title="Differ {TAKES_DIFFER}"></div>
    </div>
    <div class="dim" style="font-size:12px">Sentiment agreement — <span style="color:var(--pos)">■ {TAKES_AGREE} agree</span> · <span style="color:var(--neg)">■ {TAKES_DIFFER} differ</span>.
      <br>vs star-rating proxy — LLM correct {TAKES_LLM_VS_STAR}/{TAKES_N} ({TAKES_LLM_VS_STAR/TAKES_N*100:.0f}%) · NRC correct {TAKES_NRC_VS_STAR}/{TAKES_N} ({TAKES_NRC_VS_STAR/TAKES_N*100:.0f}%).</div>
  </div>

  __EXPLORER_HTML__
  </div><!-- /tab-explorer -->

  <div class="sub" style="margin-top:30px">Generated from classifier run · 120-review stratified sample · star-rating proxy: 4–5★ = positive · 3★ = neutral · 1–2★ = negative · LLM-vs-NRC explorer uses the two independent takes</div>
</div>

{CMP_SCRIPT}
__EXPLORER_JS__
</body>
</html>"""

html_doc = html_doc.replace("__CMP_JSON__", CMP_JSON)
html_doc = html_doc.replace("__EXPLORER_HTML__", EXPLORER["html"])
html_doc = html_doc.replace("__EXPLORER_JS__", EXPLORER["js"])
with open(OUT, "w") as f:
    f.write(html_doc)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
