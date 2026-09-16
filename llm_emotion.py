"""Take 1 — LLM sentiment + primary emotion classification.

Runs a fresh, independent LLM call per review asking for BOTH a binary
sentiment and the single most-likely primary emotion, constrained to the
NRC 8 emotion labels so it is directly comparable to the NRC lexicon scorer.

Reads the existing 120 reviews (title/text/rating), caches results.
"""
from __future__ import annotations
import json, os, time, hashlib
from openai import OpenAI

EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]

SYSTEM = """You analyze an Amazon gift-card review and return two things:
1. sentiment: strictly "positive" or "negative".
2. emotion: the single PRIMARY emotion the review most conveys, chosen ONLY
   from this list: anger, anticipation, disgust, fear, joy, sadness, surprise, trust.
Use the title AND the text together. If several emotions appear, pick the dominant one.
Return strict JSON: {"sentiment":"positive|negative","emotion":"<one of the 8>","reason":"one short sentence"}"""


def classify(t, txt, client):
    m = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Review title: {t!r}\nReview text: {txt!r}\n\nOutput JSON now:"},
    ]
    resp = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "DeepSeek-V4-Flash-0731"),
        messages=m, temperature=0.0, max_tokens=600,
    )
    msg = resp.choices[0].message
    content = msg.content or ""
    reasoning = str(getattr(msg, "reasoning", "") or "")
    raw = content if content.strip() else reasoning
    return _parse(raw, reasoning)


def _parse(raw, reasoning):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").lstrip("\n")
    d = {}
    try:
        d = json.loads(raw)
    except Exception:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e > s:
            try:
                d = json.loads(raw[s:e + 1])
            except Exception:
                d = {}
    sent = str(d.get("sentiment", "")).lower()
    if sent not in ("positive", "negative"):
        sent = "negative" if "negativ" in raw.lower() else "positive"
    emo = str(d.get("emotion", "")).lower().strip()
    if emo not in EMOTIONS:
        # try to match any of the 8 in the raw text
        found = None
        low = (raw + " " + reasoning).lower()
        for e in EMOTIONS:
            if e in low:
                found = e
                break
        emo = found or "unknown"
    return {"sentiment": sent, "emotion": emo,
            "reason": str(d.get("reason", "") or ""),
            "raw": raw[:400]}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/classifications.results_120.json")
    ap.add_argument("--cache", default="data/emotion_llm.jsonl")
    args = ap.parse_args()

    reviews = json.load(open(args.results))
    # load cache
    cache = {}
    if os.path.exists(args.cache):
        for line in open(args.cache, encoding="utf-8"):
            try:
                r = json.loads(line)
                cache[r["fp"]] = r
            except Exception:
                pass

    fp = lambda r: hashlib.sha1((r["title"] + "\x00" + r["text"]).encode()).hexdigest()
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
    done = 0
    new = 0
    out_rows = []
    for r in reviews:
        key = fp(r)
        if key in cache:
            rec = cache[key]
        else:
            res = classify(r["title"] or "", r["text"] or "", client)
            rec = {**res, "fp": key, "title": r["title"], "text": r["text"],
                   "rating": r["rating"]}
            append_cache(args.cache, rec)
            cache[key] = rec
            new += 1
            time.sleep(0.5)
        # attach ground truth label for comparison
        rec = dict(rec)
        rec["true"] = "positive" if r["rating"] >= 4 else "negative"
        rec["rating"] = r["rating"]
        out_rows.append(rec)
        done += 1
    with open(args.results.replace(".json", ".llmemo.json"), "w") as f:
        json.dump(out_rows, f, indent=2)
    print(f"processed {done} reviews ({new} new LLM calls, {done-new} cached)")
    print("saved ->", args.results.replace(".json", ".llmemo.json"))


def append_cache(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
