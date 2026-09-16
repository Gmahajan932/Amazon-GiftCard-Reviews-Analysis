"""LLM-based sentiment classifier for Amazon Gift Card reviews.

Classifies each review as POSITIVE, NEUTRAL or NEGATIVE from its title + text
using an LLM (OpenAI-compatible API), with TONE as the primary signal and
review LENGTH as a tiebreaker/weight when the tone is neutral or ambiguous.

Ground truth for evaluation comes from the review's star rating:
    rating >= 4  -> POSITIVE
    rating == 3  -> NEUTRAL
    rating <= 2  -> NEGATIVE

Usage:
    python classifier.py --sample 40            # classify N stratified reviews
    python classifier.py --eval results.json    # just print metrics + examples
"""

from __future__ import annotations
import argparse, gzip, hashlib, json, os, random, time
from openai import OpenAI

CLASSES = ["positive", "neutral", "negative"]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_reviews(path: str, limit: int | None = None) -> list[dict]:
    """Load gift-card reviews from the .jsonl.gz file."""
    reviews = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            r = json.loads(line)
            # keep only the fields we care about
            reviews.append({
                "rating": float(r.get("rating", 0)),
                "title": (r.get("title") or "").strip(),
                "text": (r.get("text") or "").strip(),
            })
    return reviews


def rating_to_label(r: float) -> str:
    """Map a star rating to a ground-truth sentiment label."""
    if r >= 4.0:
        return "positive"
    if r == 3.0:
        return "neutral"
    return "negative"  # 1, 2


def sample_stratified(reviews: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Draw ~n reviews while keeping the star-rating distribution roughly even.

    Because 84% of this dataset is 5-star, a plain random draw would give us
    almost nothing to test against on the negative side. Stratifying fixes it.
    """
    rng = random.Random(seed)
    buckets: dict[float, list[dict]] = {}
    for r in reviews:
        buckets.setdefault(r["rating"], []).append(r)
    # target = spread n across buckets, cap at what's available
    per_it = cnt = len(buckets)
    picked: list[dict] = []
    # round-robin so every rating is represented even if n is small
    while len(picked) < n:
        added = False
        for rating in sorted(buckets.keys(), reverse=True):
            b = buckets[rating]
            if b and len(picked) < n:
                picked.append(b.pop(rng.randrange(len(b))))
                added = True
        if not added:
            break  # nothing left
    rng.shuffle(picked)
    return picked

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _fingerprint(title: str, text: str) -> str:
    return hashlib.sha1((title + "\x00" + text).encode("utf-8")).hexdigest()


def load_cache(path: str) -> dict:
    cache: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    cache[rec["fp"]] = rec
                except Exception:
                    continue
    return cache


def append_cache(path: str, rec: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You classify Amazon reviews for a gift-card product into POSITIVE, NEUTRAL, or NEGATIVE.

Decision rules, in order of priority:
1. TONE is the primary signal. Judge the reviewer's sentiment from BOTH the
   title and the review text. Strong positive words (love, great, perfect,
   recommend, gift) point positive; complaints (waste, broken, hate, never
   again, scam, refused) point negative. Do not be fooled by sarcasm.
2. NEUTRAL is for genuinely even-handed, fact-only, or "it's fine / it works /
   no strong opinion" reviews where the reviewer expresses neither clear
   enthusiasm nor clear complaint. Mildly positive phrases like "decent",
   "okay", "fine", "does the job" without strong feeling should lean neutral
   rather than forced-positive.
3. LENGTH is a tiebreaker / weight. It only breaks ties or adjusts confidence
   when the tone is mixed or genuinely ambiguous:
     - A longer, detailed review that elaborates a clear stance follows that
       stance (its tone wins).
     - A long, rambling, mostly complaint-heavy review leans NEGATIVE even if
       it politely mentions one small positive — but stays NEUTRAL if praise
       and criticism are roughly balanced with no strong lean.
     - A very short, factual, no-feeling note ("it worked", "arrived") should
       be NEUTRAL unless it plainly states a real complaint or real enthusiasm.
   Tone always outweighs length: a one-word "terrible!" is still NEGATIVE,
   a one-word "love it!" is still POSITIVE.

Return strict JSON, no prose, exactly this shape:
{"tone":"positive"|"negative"|"neutral"|"mixed",
 "length":"short"|"medium"|"long",
 "classification":"positive"|"neutral"|"negative",
 "confidence":0.0-1.0,
 "reason":"one short sentence"}"""


def build_classify_prompt(review: dict) -> list[dict]:
    title = review["title"] or "(no title)"
    text = review["text"].strip() or "(no text)"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"Review title: {title!r}\nReview text: {text!r}\n\n"
                    "Output your JSON classification now."},
    ]


def classify(client: OpenAI, review: dict) -> dict:
    """Run the LLM once and return a structured classification."""
    resp = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "DeepSeek-V4-Flash-0731"),
        messages=build_classify_prompt(review),
        temperature=0.0,
        max_tokens=1200,
    )
    msg = resp.choices[0].message
    content = msg.content or ""
    # DeepSeek models emit reasoning in a separate field; if the JSON content
    # was cut off, fall back to the reasoning text rather than guessing.
    reasoning = ""
    rdata = getattr(msg, "reasoning", None)
    if rdata is not None:
        try:
            if isinstance(rdata, str):
                reasoning = rdata
            else:
                reasoning = str(rdata)
        except Exception:
            reasoning = ""
    raw = content if content.strip() else reasoning
    return _parse(raw)


def _parse(raw: str) -> dict:
    """Best-effort extraction of the JSON object from an LLM response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").lstrip("\n")
    try:
        data = json.loads(raw)
    except Exception:
        # find the first { ... } block
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            data = json.loads(raw[start:end + 1])
        else:
            data = {}
    classification = str(data.get("classification", "")).lower()
    if classification not in CLASSES:
        low = raw.lower()
        if "neutral" in low or ("negativ" not in low and "positiv" not in low):
            classification = "neutral"
        elif "negativ" in low:
            classification = "negative"
        else:
            classification = "positive"
    return {
        "tone": str(data.get("tone", "unknown")).lower(),
        "length": str(data.get("length", "unknown")).lower(),
        "classification": classification,
        "confidence": float(data.get("confidence", 0.5)),
        "reason": str(data.get("reason", "")),
        "raw": raw,
    }

# ---------------------------------------------------------------------------
# Runner (with caching + per-call sleep to be kind to the API)
# ---------------------------------------------------------------------------

def run(client: OpenAI, reviews: list[dict], cache: dict, cache_path: str,
        verbose: bool = False) -> list[dict]:
    results = []
    for review in reviews:
        fp = _fingerprint(review["title"], review["text"])
        if fp in cache:
            rec = cache[fp]
        else:
            rec = classify(client, review)
            rec["fp"] = fp
            rec["title"] = review["title"]
            rec["text"] = review["text"]
            rec["nnwords"] = len(review["text"].split())
            append_cache(cache_path, rec)
            cache[fp] = rec
            time.sleep(0.6)  # light rate-limit
        rec.setdefault("rating", review["rating"])
        rec["rating"] = review["rating"]
        rec["true"] = rating_to_label(review["rating"])
        results.append(rec)
    return results

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(results: list[dict]) -> dict:
    """Multi-class metrics over CLASSES (positive/neutral/negative)."""
    labels = CLASSES
    conf = {t: {p: 0 for p in labels} for t in labels}
    detail = []
    for r in results:
        pred, true = r["classification"], r["true"]
        if pred not in labels:
            pred = "neutral"
        conf[true][pred] += 1
        detail.append({**r, "correct": pred == true})
    n = len(results)
    correct = sum(conf[t][t] for t in labels)
    acc = correct / max(1, n)

    per_class = {}
    for c in labels:
        tp = conf[c][c]
        fp = sum(conf[t][c] for t in labels if t != c)
        fn = sum(conf[c][p] for p in labels if p != c)
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(1e-9, prec + rec)
        per_class[c] = {"tp": tp, "fp": fp, "fn": fn,
                        "precision": round(prec, 4), "recall": round(rec, 4),
                        "f1": round(f1, 4)}
    macro_f1 = sum(per_class[c]["f1"] for c in labels) / len(labels)
    return {
        "n": n,
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion": conf,
        "confusion_flat": {f"{t}->{p}": v for t in labels for p in labels
                           for v in [conf[t][p]]},
        "detail": detail,
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/Gift_Cards.jsonl.gz")
    ap.add_argument("--cache", default="data/classifications_3way.jsonl",
                    help="cache file; use a fresh name when the label scheme changes")
    ap.add_argument("--sample", type=int, default=40,
                    help="classify a stratified sample of this many reviews")
    ap.add_argument("--limit", type=int, default=None,
                    help="max rows to scan from the dataset")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval", metavar="RESULTS_JSON",
                    help="skip classification; just print metrics from saved JSON")
    args = ap.parse_args()

    if args.eval:
        with open(args.eval) as f:
            results = json.load(f)
        m = evaluate(results)
        print(json.dumps({k: v for k, v in m.items() if k != "detail"},
                         indent=2))
        _show_errors(m["detail"])
        return

    reviews = load_reviews(args.data, args.limit)
    print(f"Loaded {len(reviews)} reviews from {args.data}")
    sample = sample_stratified(reviews, args.sample, seed=args.seed)
    ratings = sorted({r["rating"] for r in sample})
    print(f"Stratified sample: {args.sample} reviews ({ratings} ratings)\n")

    client = OpenAI(base_url=os.environ["LLM_BASE_URL"],
                    api_key=os.environ["LLM_API_KEY"])
    cache = load_cache(args.cache)
    results = run(client, sample, cache, args.cache)

    out = args.cache.replace(".jsonl", f".results_{args.sample}.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    m = evaluate(results)
    print(json.dumps({k: v for k, v in m.items() if k != "detail"}, indent=2))
    _show_errors(m["detail"])
    print(f"\nSaved detail -> {out}")


def _show_errors(detail: list[dict], k: int = 12) -> None:
    wrong = [d for d in detail if not d["correct"]]
    print(f"\n=== {len(wrong)} mismatches vs. star-rating ground truth ===")
    for d in wrong[:k]:
        print(f"- truth={d['true']:8} pred={d['classification']:8} "
              f"conf={d['confidence']:.2f} tone={d['tone']:8} len={d['length']:6} "
              f"| {d['title'][:40]!r}")


if __name__ == "__main__":
    main()
