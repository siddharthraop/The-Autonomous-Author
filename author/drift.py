"""Daily drift check (design doc §5.6): compare the last 10 runs with a baseline of 20."""
import statistics

THRESHOLDS = {"quality": 1.0, "review": 0.15, "grounding": 0.05}


def check(rows, recent=10, baseline=20):
    drafts = [r for r in rows if r.get("type") == "draft" and r.get("confidence") is not None]
    reviews = [r for r in rows if r.get("type") == "review" and r.get("edit_ratio") is not None]
    findings = []
    if len(drafts) < recent + baseline:
        return {"enough_data": False, "drafts": len(drafts), "needed": recent + baseline, "findings": []}
    base, last = drafts[:baseline], drafts[-recent:]
    b, l = statistics.mean(r["confidence"] for r in base), statistics.mean(r["confidence"] for r in last)
    if b - l >= THRESHOLDS["quality"]:
        findings.append(("Quality drift", f"mean confidence of the last {recent} runs is {l:.2f}, baseline {b:.2f}"))
    if len(reviews) >= recent + baseline:
        rb = statistics.median(r["edit_ratio"] for r in reviews[:baseline])
        rl = statistics.median(r["edit_ratio"] for r in reviews[-recent:])
        if rl - rb >= THRESHOLDS["review"]:
            findings.append(("Review drift", f"median edit ratio {rl:.2f}, baseline {rb:.2f}: writers rewrite more"))
    ph = sum(r.get("placeholders", 0) for r in last)
    ns = sum(r.get("new_sentences", 0) for r in last) or 1
    if ph / ns > THRESHOLDS["grounding"]:
        findings.append(("Grounding drift", f"{ph} of {ns} new sentences in the last {recent} runs became questions"))
    for key in ("model_id", "prompt_version", "vale_package"):
        bv = {r.get(key) for r in base}
        for r in last:
            if r.get(key) not in bv:
                findings.append(("Configuration change", f"{key} {r.get(key)} in run {r['run_id']} is not in the baseline ({', '.join(map(str, bv))}); replay the evaluation set"))
                break
    types = {t for r in base for t in (r.get("change_types") or "").split(",")}
    new_types = {t for r in last for t in (r.get("change_types") or "").split(",")} - types - {""}
    if new_types:
        findings.append(("Input drift", f"change types not in the baseline: {', '.join(sorted(new_types))}"))
    return {"enough_data": True, "baseline_mean": round(b, 2), "recent_mean": round(l, 2),
            "runs": [r["run_id"] for r in last], "findings": findings}
