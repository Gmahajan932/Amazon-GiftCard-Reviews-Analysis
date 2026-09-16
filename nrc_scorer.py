"""Take 2 — NRC Emotion Lexicon word-level scorer.

Each review's words are looked up in the NRC Emotion Lexicon. We aggregate:
  * sentiment  -> positive if positive-word associations >= negative-words, else negative
  * emotion    -> the single (of 8) emotion with the most word associations
  * scores     -> full per-category association counts

Emotions (NRC 8): anger, anticipation, disgust, fear, joy, sadness, surprise, trust.
"""
from __future__ import annotations
import json, os, re
from collections import Counter

LEXICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "NRC-Emotion-Lexicon-Wordlevel-v0.92.txt")
EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def load_lexicon(path: str = LEXICON_PATH) -> dict[str, set[str]]:
    """Return {category: set(words)} including positive/negative."""
    cat_words: dict[str, set[str]] = {c: set() for c in EMOTIONS + ["positive", "negative"]}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            word, cat, flag = parts[0].strip().lower(), parts[1].strip(), parts[2].strip()
            if cat in cat_words and flag == "1":
                cat_words[cat].add(word)
    return cat_words


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def score_text(text: str, lex: dict[str, set[str]]) -> dict:
    """Aggregate NRC associations for one review's text."""
    counts: Counter[str] = Counter()
    hits = 0
    for tok in tokenize(text):
        for cat in EMOTIONS + ["positive", "negative"]:
            if tok in lex[cat]:
                counts[cat] += 1
                hits += 1
    return dict(counts)


def decide(*, counts: dict, neg_offset: int = 0) -> dict:
    """Derive sentiment + primary emotion from aggregated NRC counts."""
    pos = counts.get("positive", 0)
    neg = counts.get("negative", 0)
    sentiment = "positive" if pos >= neg + neg_offset else "negative"
    # primary emotion = highest of the 8 (tie -> alpha/stable order)
    emo_scores = {e: counts.get(e, 0) for e in EMOTIONS}
    emotion = max(emo_scores, key=lambda e: (emo_scores[e], -EMOTIONS.index(e)))
    return {"sentiment": sentiment,
            "emotion": emotion,
            "emotion_conf": emo_scores[emotion],
            "pos_hits": pos, "neg_hits": neg,
            "scores": {e: emo_scores[e] for e in EMOTIONS},
            "total_hits": int(pos + neg)}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/classifications.results_120.json")
    out = ap.parse_args().results
    base = out.replace(".json", "")
    reviews = json.load(open(out))
    lex = load_lexicon()
    rows = []
    for r in reviews:
        counts = score_text(r.get("text") or "", lex)
        d = decide(counts=counts)
        rows.append({**r, "nrc": d})
    dest = f"{base}.nrc.json"
    with open(dest, "w") as f:
        json.dump(rows, f, indent=2)
    # quick summary
    from collections import Counter as C
    sent = C(d["nrc"]["sentiment"] for d in rows)
    emo = C(d["nrc"]["emotion"] for d in rows)
    print("NRC sentiment:", dict(sent))
    print("NRC primary emotion:", dict(emo))
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
