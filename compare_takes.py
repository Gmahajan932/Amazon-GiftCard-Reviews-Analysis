"""Merge Take 1 (LLM emotion) + Take 2 (NRC lexicon) and compare.

Produces:
  * a merged per-review file with both takes' sentiment + emotion + truth
  * agreement stats:  LLM-vs-NRC sentiment, LLM-vs-NRC emotion,
                      each take vs star-rating ground-truth sentiment,
                      per-review agreement/conflict flags
"""
from __future__ import annotations
import json, os
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
NRC = os.path.join(ROOT, "data", "classifications.results_120.nrc.json")
LLM = os.path.join(ROOT, "data", "classifications.results_120.llmemo.json")
OUT = os.path.join(ROOT, "data", "takes_merged.json")

EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]


def load():
    nrc = {r["fp"]: r for r in json.load(open(NRC))}
    llm = {r["fp"]: r for r in json.load(open(LLM))}
    rows = []
    for fp, r in llm.items():
        n = nrc.get(fp)
        if n is None:
            print("WARN: no NRC for", fp)
            continue
        rows.append({
            "fp": fp, "title": r["title"], "text": r["text"],
            "true": r["true"], "rating": r["rating"],
            "llm": {"sentiment": r["sentiment"], "emotion": r["emotion"],
                    "reason": r.get("reason", "")},
            "nrc": {"sentiment": n["nrc"]["sentiment"], "emotion": n["nrc"]["emotion"],
                    "scores": n["nrc"]["scores"], "total_hits": n["nrc"]["total_hits"]},
        })
    return rows


def sentiment_agree(a, b):
    return a == b


def main():
    rows = load()
    # ---- sentiment agreement LLM vs NRC ----
    sent_agree = sum(1 for r in rows if sentiment_agree(r["llm"]["sentiment"], r["nrc"]["sentiment"]))
    # ---- emotion agreement ----
    emo_agree = sum(1 for r in rows if r["llm"]["emotion"] == r["nrc"]["emotion"])
    emo_agree_valid = sum(1 for r in rows
                          if r["llm"]["emotion"] in EMOTIONS and r["nrc"]["emotion"] in EMOTIONS
                          and r["llm"]["emotion"] == r["nrc"]["emotion"])
    emo_valid = sum(1 for r in rows if r["llm"]["emotion"] in EMOTIONS)

    # ---- each take vs star-rating ground-truth sentiment ----
    llm_vs_true = sum(1 for r in rows if r["llm"]["sentiment"] == r["true"])
    nrc_vs_true = sum(1 for r in rows if r["nrc"]["sentiment"] == r["true"])

    n = len(rows)
    summary = {
        "n": n,
        "sentiment_agreement_llm_nrc": round(sent_agree / n, 4),
        "sentiment_agreement_n": sent_agree,
        "emotion_agreement_llm_nrc": round(emo_agree / n, 4),
        "emotion_agreement_n": emo_agree,
        "emotion_agreement_valid_only": round(emo_agree_valid / max(1, emo_valid), 4),
        "emotion_valid_pairs_n": emo_valid,
        "llm_sentiment_vs_star": round(llm_vs_true / n, 4),
        "llm_sentiment_vs_star_n": llm_vs_true,
        "nrc_sentiment_vs_star": round(nrc_vs_true / n, 4),
        "nrc_sentiment_vs_star_n": nrc_vs_true,
        # both take agreement with each other AND with stars (perfect triple-match)
    }

    # per-row flags
    for r in rows:
        r["sent_agree"] = r["llm"]["sentiment"] == r["nrc"]["sentiment"]
        r["emo_agree"] = r["llm"]["emotion"] == r["nrc"]["emotion"]
        r["both_vs_star"] = r["llm"]["sentiment"] == r["true"] == r["nrc"]["sentiment"]

    with open(OUT, "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print("saved ->", OUT)

    # confusion of LLM sentiment vs NRC sentiment
    print("\n--- LLM-sent vs NRC-sent confusion ---")
    cm = Counter((r["llm"]["sentiment"], r["nrc"]["sentiment"]) for r in rows)
    for (a, b), c in sorted(cm.items()):
        print(f"  LLM={a:8} NRC={b:8}: {c}")

    # emotion distribution per take
    print("\n--- LLM emotion distribution ---")
    print(dict(Counter(r["llm"]["emotion"] for r in rows)))
    print("\n--- NRC emotion distribution ---")
    print(dict(Counter(r["nrc"]["emotion"] for r in rows)))


if __name__ == "__main__":
    main()
