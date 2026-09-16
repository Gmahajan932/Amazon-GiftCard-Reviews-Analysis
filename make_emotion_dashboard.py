"""Generate an emotions + takes-comparison dashboard from the merged data.

Reads data/takes_merged.json (which holds both the LLM take and the NRC take,
plus star-rating ground truth) and emits data/emotion_dashboard.html with the
agreement analysis, emotion distributions, and per-review comparison cards.
"""
from __future__ import annotations
import json, html, os
from collections import Counter

ROOT = "/Users/gaurimahajan/git-and-github-lab"
SRC = os.path.join(ROOT, "data", "takes_merged.json")
OUT = os.path.join(ROOT, "data", "emotion_dashboard.html")

data = json.load(open(SRC))
rows = data["rows"]
M = data["summary"]
EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]
EMO_COLORS = {"anger":"#f43f5e","anticipation":"#f59e0b","disgust":"#84cc16","fear":"#a855f7",
              "joy":"#fbbf24","sadness":"#60a5fa","surprise":"#22d3ee","trust":"#34d399"}

def esc(s): return html.escape(str(s))
def pct(a,b): return 100.0*a/b if b else 0.0

n = len(rows)

# emotion distribution per take
llm_emo = Counter(r["llm"]["emotion"] for r in rows)
nrc_emo = Counter(r["nrc"]["emotion"] for r in rows)

def emo_bar(counts):
    segs=[]
    for e in EMOTIONS:
        if counts.get(e,0)>0:
            segs.append(f'<div class="seg" style="width:{pct(counts[e],n):.1f}%;background:{EMO_COLORS[e]}" title="{e}: {counts[e]}"></div>')
    return '<div class="bar stacked">'+"".join(segs)+'</div>'

def emo_legend(counts):
    return "".join(f'<span class="lg"><i style="background:{EMO_COLORS[e]}"></i>{e} <b>{counts.get(e,0)}</b></span>'
                   for e in EMOTIONS if counts.get(e,0))

def donut(frac, color, labeltxt, sub):
    r=28; c=2*3.14159*r; dash=frac*c
    return f'''<div class="donutwrap">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="{r}" fill="none" stroke="#334155" stroke-width="12"/>
        <circle cx="40" cy="40" r="{r}" fill="none" stroke="{color}" stroke-width="12"
            stroke-dasharray="{dash:.1f} {c:.1f}" stroke-linecap="round" transform="rotate(-90 40 40)"/>
      </svg>
      <div class="donutlabel">{frac*100:.0f}%</div>
      <div class="donuttxt">{labeltxt}</div><div class="donutsub dim">{sub}</div></div>'''

# agreement cards
sent_agree_rows = [r for r in rows if r["llm"]["sentiment"]==r["nrc"]["sentiment"]]
sent_disagree = [r for r in rows if r["llm"]["sentiment"]!=r["nrc"]["sentiment"]]
emo_agree_rows = [r for r in rows if r["llm"]["emotion"]==r["nrc"]["emotion"]]
emo_disagree = [r for r in rows if r["llm"]["emotion"]!=r["nrc"]["emotion"]]
both_vs_star = [r for r in rows if r["both_vs_star"]]

def card(title, text, chips_html, reason):
    return f'''<div class="card">
      <div class="ctitle">{esc(title) or '(no title)'}</div>
      <div class="ctext">{esc(text[:200])}{'…' if len(text)>200 else ''}</div>
      <div class="chips">{chips_html}</div>
      <div class="creason"><b>LLM:</b> {esc(reason)}</div>
    </div>'''

def chips_for(r):
    return (f'<span class="chip star">rating {int(r["rating"])}★</span>'
            f'<span class="chip truth">truth: {r["true"]}</span>'
            f'<span class="chip llm {r["llm"]["sentiment"]}">LLM: {r["llm"]["sentiment"]}</span>'
            f'<span class="chip nrc {r["nrc"]["sentiment"]}">NRC: {r["nrc"]["sentiment"]}</span>'
            f'<span class="chip emo">{r["llm"]["emotion"]} (LLM)</span>'
            f'<span class="chip emo2">{r["nrc"]["emotion"]} (NRC)</span>')

def grid(items):
    return '<div class="cards">' + "".join(card(r["title"], r["text"], chips_for(r), r["llm"]["reason"]) for r in items) + '</div>'

def sentim_cm():
    # LLM sentiment (rows) vs NRC sentiment (cols)
    cm = Counter((r["llm"]["sentiment"], r["nrc"]["sentiment"]) for r in rows)
    def cell(a,b): return cm.get((a,b),0)
    return '''<div class="cm">
      <div class="cmcell cmhead">LLM ↓ · NRC →</div><div class="cmcell cmhead">positive</div><div class="cmcell cmhead">negative</div>
      <div class="cmcell cmhead">positive</div><div class="cmcell cmpp">%d</div><div class="cmcell cmoff">%d</div>
      <div class="cmcell cmhead">negative</div><div class="cmcell cmoff">%d</div><div class="cmcell cmnn">%d</div>
    </div>''' % (cell("positive","positive"), cell("positive","negative"),
                 cell("negative","positive"), cell("negative","negative"))

DOC = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Emotion &amp; Takes Comparison — Gift Card Classifier</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --card2:#243247; --line:#334155;
           --txt:#e2e8f0; --dim:#94a3b8; --accent:#f472b6; --pos:#16a34a; --neg:#dc2626; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:var(--txt); line-height:1.45; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  h2 {{ font-size:16px; color:var(--accent); margin:30px 0 12px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
  h3 {{ font-size:14px; margin:4px 0 10px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:22px; }}
  .dim {{ color:var(--dim); font-weight:400; font-size:12px; }}
  .grid {{ display:grid; gap:14px; }} .g4 {{ grid-template-columns:repeat(4,1fr); }} .g2 {{ grid-template-columns:repeat(2,1fr); }}
  @media(max-width:720px) {{ .g4{{grid-template-columns:repeat(2,1fr);}} .g2{{grid-template-columns:1fr;}} }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; text-align:center; padding:18px 12px; }}
  .kpi .val {{ font-size:26px; font-weight:700; color:var(--accent); }}
  .kpi.good .val {{ color:var(--pos); }} .kpi.low .val {{ color:var(--neg); }}
  .kpi .lab {{ color:var(--dim); font-size:11px; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }}
  .kpi .subl {{ font-size:11px; color:var(--dim); margin-top:2px; }}
  .bar {{ height:24px; background:#334155; border-radius:6px; overflow:hidden; display:flex; }}
  .seg {{ height:100%; }}
  .lg {{ display:inline-flex; align-items:center; gap:6px; margin:6px 14px 6px 0; font-size:12px; color:var(--dim); }}
  .lg i {{ width:10px; height:10px; border-radius:3px; display:inline-block; }}
  .donuts {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .donutwrap {{ text-align:center; background:var(--card2); padding:12px; border-radius:10px; width:150px; }}
  .donutwrap svg {{ display:block; margin:0 auto; }} .donutlabel {{ margin-top:-62px; font-size:13px; font-weight:700; }}
  .donuttxt {{ font-size:12px; margin-top:8px; }} .donutsub {{ font-size:11px; color:var(--dim); }}
  .cards {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:6px; }}
  @media(max-width:720px) {{ .cards{{grid-template-columns:1fr;}} }}
  .ctitle {{ font-weight:600; font-size:13px; margin-bottom:3px; }}
  .ctext {{ font-size:12px; color:#cbd5e1; }} .creason {{ font-size:11px; color:var(--dim); margin-top:6px; font-style:italic; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }}
  .chip {{ font-size:10px; padding:2px 7px; border-radius:20px; background:#334155; }}
  .chip.positive {{ background:#14532d; }} .chip.negative {{ background:#7f1d1d; }}
  .chip.llm {{ outline:1px solid var(--accent); }} .chip.nrc {{ outline:1px solid #38bdf8; }}
  .chip.star {{ background:#78350f; }} .chip.truth {{ background:#1e3a8a; }}
  .chip.emo {{ background:#3b0764; }} .chip.emo2 {{ background:#164e63; }}
  .cm {{ display:grid; grid-template-columns:auto auto auto; gap:8px; }}
  .cmcell {{ padding:14px; text-align:center; border-radius:10px; font-size:20px; font-weight:700; }}
  .cmhead {{ font-size:12px; color:var(--dim); font-weight:600; display:flex; align-items:center; justify-content:center; }}
  .cmpp {{ background:#14532d; }} .cmnn {{ background:#14532d; }} .cmoff {{ background:#7f1d1d; }}
  .note {{ background:#1e293b; border-left:3px solid var(--accent); padding:10px 14px; border-radius:8px; font-size:13px; color:#cbd5e1; margin-top:12px; }}
  .note b {{ color:var(--txt); }}
</style></head><body><div class="wrap">

<h1>Emotion &amp; Takes Comparison</h1>
<div class="sub">Take 1 = LLM (prompt) · Take 2 = NRC Emotion Lexicon (rule-based) · compared against each other and the star-rating proxy</div>

<div class="grid g4">
  <div class="kpi good"><div class="val">{pct(M["sentiment_agreement_n"],n):.0f}%</div><div class="lab">LLM↔NRC sentiment</div><div class="subl">{M["sentiment_agreement_n"]}/{n} reviews</div></div>
  <div class="kpi low"><div class="val">{pct(M["emotion_agreement_n"],n):.0f}%</div><div class="lab">LLM↔NRC emotion</div><div class="subl">{M["emotion_agreement_n"]}/{n} reviews</div></div>
  <div class="kpi good"><div class="val">{pct(M["llm_sentiment_vs_star_n"],n):.0f}%</div><div class="lab">LLM vs stars</div><div class="subl">{M["llm_sentiment_vs_star_n"]}/{n}</div></div>
  <div class="kpi low"><div class="val">{pct(M["nrc_sentiment_vs_star_n"],n):.0f}%</div><div class="lab">NRC vs stars</div><div class="subl">{M["nrc_sentiment_vs_star_n"]}/{n}</div></div>
</div>

<h2>What this tells us</h2>
<div class="grid g2">
  <div class="card">
    <h3>LLM sentiment vs NRC sentiment</h3>
    {sentim_cm()}
    <div class="dim" style="margin-top:10px">Row = LLM, column = NRC. NRC labels far more reviews "positive" (its lexicon tags neutral gift-card words as positive).</div>
  </div>
  <div class="card">
    <h3>Both takes agree with stars</h3>
    <div class="donuts" style="justify-content:space-around">
      {donut(len(both_vs_star)/n, '#34d399', f"{len(both_vs_star)} / {n}", "LLM + NRC both match stars")}
      {donut(len(sent_agree_rows)/n, '#f472b6', f"{len(sent_agree_rows)} / {n}", "Sentiment agree LLM↔NRC")}
      {donut(len(emo_agree_rows)/n, '#38bdf8', f"{len(emo_agree_rows)} / {n}", "Emotion agree LLM↔NRC")}
    </div>
  </div>
</div>

<h2>Primary emotion — LLM take</h2>
<div class="card">{emo_bar(llm_emo)}<div style="margin-top:10px">{emo_legend(llm_emo)}</div></div>

<h2>Primary emotion — NRC take</h2>
<div class="card">{emo_bar(nrc_emo)}<div style="margin-top:10px">{emo_legend(nrc_emo)}</div></div>

<h2>Where LLM &amp; NRC disagree on sentiment ({len(sent_disagree)} reviews)</h2>
{grid(sent_disagree[:12])}

<h2>Where both agree ({len(sent_agree_rows)} reviews) — top examples</h2>
{grid(sent_agree_rows[:8])}

<div class="note"><b>Why they diverge:</b> the NRC Emotion Lexicon was built as a general English word-association resource. In a gift-card/catalog category it tags neutral product vocabulary — <b>gift, money, balance, store, customer</b> — as "positive," so a naive word-count sentiment scores almost everything positive. The LLM reads the whole phrase and the star-vs-text relationship, making it far more sensitive to genuine complaints. Raw NRC word-sums are a weak sentiment signal in this domain (45% vs stars); they are better suited to descriptive emotional-intensity profiling than to positive/negative classification.</div>

<div class="dim" style="margin-top:30px">Both takes' outputs are kept per-review in data/takes_merged.json.</div>
</div></body></html>"""

with open(OUT,"w") as f: f.write(DOC)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
