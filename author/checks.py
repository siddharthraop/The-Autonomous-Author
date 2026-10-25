"""Tools 4 to 6: the fixed checks. Same input, same result, every time.

They also run as the required docs-checks workflow on every docs pull request,
so a writer's edit is tested as strictly as the agent's draft.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

from .pages import SUBS, doc_files, old_value_re, term
from .sentences import PLACEHOLDER, added_lines, contains, literals, norm, split
import re


# Tool 4 ------------------------------------------------------------------
def check_style(repo, changed):
    """Vale with the Google package, on changed lines only. `changed` maps path -> set of line numbers."""
    vale = shutil.which("vale")
    res = {"ran": bool(vale), "errors": 0, "warnings": 0, "alerts": []}
    if not vale or not changed:
        return res
    files = [p for p in changed if p.endswith(".md")]
    if not files:
        return res
    r = subprocess.run([vale, "--output=JSON", "--no-exit", *files], cwd=repo, capture_output=True, text=True)
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        res["ran"] = False
        res["note"] = (r.stderr or r.stdout)[:300]
        return res
    for path, alerts in data.items():
        rel = str(pathlib.Path(path)) if not pathlib.Path(path).is_absolute() else str(pathlib.Path(path).relative_to(repo))
        for a in alerts:
            if a["Line"] in changed.get(rel, set()):
                sev = a["Severity"]
                res["errors" if sev == "error" else "warnings"] += sev in ("error", "warning")
                res["alerts"].append({"path": rel, "line": a["Line"], "rule": a["Check"], "severity": sev,
                                      "message": a["Message"]})
    return res


# Tool 5 ------------------------------------------------------------------
def check_grounding(repo, base_text, items, source_map, sources):
    """Source, literals, coverage and stale values.

    base_text: path -> page text before the draft. source_map: list of {text, sources, origin}.
    sources: ID -> text of that source.
    """
    root = pathlib.Path(repo)
    sentences = []
    for path in doc_files(repo) + [SUBS]:
        new = (root / path).read_text()
        if path == SUBS:
            continue
        for line, s in split(base_text.get(path, ""), new):
            sentences.append({"path": path, "line": line, "text": s})
    by_text = {norm(e["text"]): e for e in source_map}

    def entry_for(s):
        n = norm(s)
        if n in by_text:
            return by_text[n]
        for k, e in by_text.items():
            if k and (k in n or n in k) and min(len(k), len(n)) > 12:
                return e
        return None

    for s in sentences:
        ph = PLACEHOLDER.search(s["text"])
        if ph:
            s.update(status="question", question=ph.group(1).strip(), sources=[])
            e = entry_for(s["text"])
            s["sources"] = e["sources"] if e else []
            continue
        e = entry_for(s["text"])
        if not e:
            s.update(status="fail", reason="no source map entry", sources=[])
            continue
        s["sources"], s["origin"] = e["sources"], e.get("origin", "model")
        missing = [x for x in e["sources"] if x not in sources]
        if not e["sources"] or missing:
            s.update(status="fail", reason=f"source not found: {', '.join(missing) or 'none cited'}")
            continue
        pool = " ".join(sources[x] for x in e["sources"]).lower()
        lits = literals(s["text"])
        bad = [l for l in lits if not contains(pool, l)]
        s["literals"] = f"{len(lits) - len(bad)}/{len(lits)}"
        s.update(status="fail", reason=f"literal not in source: {', '.join(bad)}") if bad else s.update(status="pass")

    present = [s for s in sentences if s["status"] in ("pass", "question")]
    covered = {c for s in present for c in s.get("sources", [])}
    covered |= {e["sources"][0] for e in source_map if e.get("origin", "").startswith("R-") and e["sources"]}
    for s in present:
        covered |= set(re.findall(r"\bC\d+\b", s.get("question", "")))
    coverage = {it.id: it.id in covered for it in items}

    stale = []
    for it in [i for i in items if i.kind == "default"]:
        rx = old_value_re(it)
        for path in doc_files(repo):
            for n, line in enumerate((root / path).read_text().splitlines(), 1):
                if "{{" not in line and rx.search(line) and re.search(term(it), line, re.I) \
                        and not PLACEHOLDER.search(line) and it.attribute == "":
                    if not _old_value_still_true(it, items):
                        stale.append({"item": it.id, "path": path, "line": n, "text": line.strip()})
        subs = (root / SUBS).read_text()
        m = re.search(rf"^\s*{it.key}\s*:\s*(.*)$", subs, re.M)
        if m and rx.search(m.group(1)):
            stale.append({"item": it.id, "path": SUBS, "line": 0, "text": m.group(0).strip()})
    return {"sentences": sentences, "coverage": coverage, "stale": stale}


def _old_value_still_true(item, items):
    """An old default stays true when the change keeps it for some readers (for example legacy_default)."""
    return any(i.name == item.name and i.kind == "attribute" and i.new == item.old for i in items)


# Tool 6 ------------------------------------------------------------------
def check_build(repo):
    out = tempfile.mkdtemp(prefix="author-build-")
    r = subprocess.run(["python", "-m", "sphinx", "-W", "-q", "-b", "html", "docs", out], cwd=repo,
                       capture_output=True, text=True)
    res = {"build": r.returncode == 0, "build_log": (r.stderr or "")[-1200:], "links_ran": False,
           "links_ok": True, "broken": [], "html": out}
    lychee = shutil.which("lychee")
    if res["build"] and lychee:
        import os
        args = [lychee, "--no-progress", "--format", "json"]
        if os.environ.get("AUTHOR_LYCHEE_ONLINE") != "1":
            args.append("--offline")
        r2 = subprocess.run(args + [f"{out}/**/*.html"], capture_output=True, text=True)
        res["links_ran"] = True
        try:
            data = json.loads(r2.stdout)
            res["links_total"] = data.get("total", 0)
            res["broken"] = [e.get("url") for v in (data.get("error_map") or data.get("fail_map") or {}).values() for e in v]
        except json.JSONDecodeError:
            res["broken"] = [] if r2.returncode == 0 else ["lychee output unreadable"]
        res["links_ok"] = not res["broken"]
    return res


def changed_lines(repo, base_text):
    root = pathlib.Path(repo)
    out = {}
    for path in doc_files(repo):
        lines = {n for n, _ in added_lines(base_text.get(path, ""), (root / path).read_text())}
        if lines:
            out[path] = lines
    return out
