"""Tool 7, part one: the confidence score (design doc §5.5). Computed from check results only."""

WEIGHTS = {"grounding": 3.5, "coverage": 2.5, "stale": 1.5, "style": 1.5, "build": 1.0}


def score(grounding, style, build):
    sents = grounding["sentences"]
    grounded = sum(s["status"] in ("pass", "question") for s in sents)
    questions = sum(s["status"] == "question" for s in sents)
    cov = grounding["coverage"]
    parts = {
        "grounding": WEIGHTS["grounding"] * (grounded / len(sents) if sents else 1),
        "coverage": WEIGHTS["coverage"] * (sum(cov.values()) / len(cov) if cov else 1),
        "stale": WEIGHTS["stale"] if not grounding["stale"] else 0.0,
        # A check that did not run earns nothing: the score only reflects checks that ran.
        "style": max(0.0, WEIGHTS["style"] - 0.5 * style["errors"] - 0.1 * style["warnings"]) if style["ran"] else 0.0,
        "build": WEIGHTS["build"] if build["build"] and build["links_ran"] and build["links_ok"] else 0.0,
    }
    parts = {k: round(v, 1) for k, v in parts.items()}
    penalty = round(0.5 * questions, 1)
    total = max(1.0, round(sum(parts.values()) - penalty, 1))
    label = "ready for review" if total >= 8.5 else "review closely" if total >= 6.0 else "needs writer"
    if questions and label == "ready for review":
        label = "review closely"  # open questions always need a person
    return {"total": total, "parts": parts, "questions": questions, "penalty": penalty, "label": label}
