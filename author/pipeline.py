"""The agent loop (design doc §5.4): read, find, rules, draft, check, revise at most twice, score, report."""
import datetime as dt
import json
import pathlib
import re
import time
import uuid

from . import PROMPT_VERSION
from .change import read_change, commit_messages, ticket_ref
from .checks import changed_lines, check_build, check_grounding, check_style
from .model import NoModel
from .pages import SUBS, doc_files, find_pages
from .rules import apply_rules
from .score import score
from .sentences import PLACEHOLDER, norm

MAX_REVISIONS = 2


def _flex(sentence):
    """Regex that finds a sentence across line wraps."""
    words = [re.escape(w) for w in sentence.split()]
    return re.compile(r"\s+".join(words)) if words else None


def _replace_sentence(root, path, old, new):
    p = root / path
    text = p.read_text()
    rx = _flex(old)
    if rx and rx.search(text):
        p.write_text(rx.sub(lambda m: new, text, count=1))
        return True
    return False


def _insert_after_paragraph(root, path, line, block):
    p = root / path
    lines = p.read_text().splitlines()
    i, fence = max(0, line - 1), False
    for j in range(0, i + 1):
        if lines[j].strip().startswith("```"):
            fence = not fence
    while i < len(lines) and (fence or lines[i].strip()):
        if lines[i].strip().startswith("```") and i != line - 1:
            fence = not fence
        i += 1
    lines[i:i] = ["", block] if i < len(lines) else ["", block]
    p.write_text("\n".join(lines) + "\n")


def _prompt(items, ticket, pr_body, pages, rule_edits, extra=""):
    parts = ["## Change items"] + [f"{i.id} ({i.kind}): {i.text} Evidence: {' | '.join(i.evidence)}" for i in items]
    if ticket:
        parts += ["## T1 doc ticket", json.dumps({k: ticket.get(k) for k in ("ref", "title", "doc_type", "audience", "pages", "text")})]
    if pr_body:
        parts += ["## S-PR description", pr_body[:3000]]
    parts += ["## Edits already made by fixed rules"] + [f"{e['rule']} {e['path']}: {e['after']}" for e in rule_edits]
    for pid, (path, text) in pages.items():
        numbered = "\n".join(f"{n:>3} {l}" for n, l in enumerate(text.splitlines(), 1))
        parts += [f"## {pid} {path}", numbered]
    return "\n\n".join(parts) + ("\n\n" + extra if extra else "")


def draft(repo, base, head, model=None, ticket=None, pr=None, change_author=None, gh=None, ticket_file=None):
    from .ticket import read_ticket
    t0 = time.time()
    model = model or NoModel()
    root = pathlib.Path(repo)
    items, diff = read_change(repo, base, head)
    run = {"run_id": uuid.uuid4().hex[:12], "type": "draft", "base": base, "head": head,
           "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "model": model.id, "prompt_version": PROMPT_VERSION, "code_pr": (pr or {}).get("number"),
           "change_author": change_author, "items": [i.to_dict() for i in items], "revisions": 0,
           "revised": [], "rejected": [], "edits": []}
    if not items:
        run.update(result="no docs change", seconds=round(time.time() - t0, 1))
        return run
    ref = ticket or ticket_ref((pr or {}).get("body")) or ticket_ref(commit_messages(repo, base, head))
    tk = read_ticket(ref, gh=gh, local=ticket_file)
    run["ticket"] = tk
    base_text = {p: (root / p).read_text() for p in doc_files(repo)}
    base_subs = (root / SUBS).read_text()
    hits = find_pages(repo, items, scope=(tk or {}).get("pages"))
    run["hits"] = hits
    page_paths = sorted({h["path"] for h in hits if h["path"] != SUBS})
    pages = {f"P{n}": (p, base_text[p]) for n, p in enumerate(page_paths, 1)}
    pid = {p: k for k, (p, _) in pages.items()}

    sources = {i.id: i.source_text() for i in items}
    index = {i.id: f"code change, `{i.path}` line {i.line}" for i in items}
    for k, (p, t) in pages.items():
        sources[k], index[k] = t, f"`{p}` at `{head[:7]}`, before the draft"
    sources["S-SUBS"], index["S-SUBS"] = base_subs, f"`{SUBS}` at `{head[:7]}`"
    if tk:
        sources["T1"] = tk.get("text", "") + " " + tk.get("title", "")
        index["T1"] = f"doc ticket {tk['ref']}: doc type {tk.get('doc_type', 'not set')}, audience {tk.get('audience', 'not set')}"
    if pr and pr.get("body"):
        sources["S-PR"], index["S-PR"] = pr["body"], f"code PR #{pr['number']} description"
    run["source_index"] = index
    run["sources"] = sources

    source_map = []
    rule_edits = apply_rules(repo, items)
    for e in rule_edits:
        run["edits"].append({"origin": e["rule"], "path": e["path"], "line": e.get("line"), "items": [e["item"]],
                             "why": "substitution updated once" if e["rule"] == "R-01" else "typed copy replaced with the substitution"})
        if e["rule"] == "R-03":
            source_map.append({"text": e["after"], "sources": [e["item"], pid.get(e["path"], "S-SUBS")], "origin": e["rule"]})

    # Model step: draft.
    rule_covered = {e["item"] for e in rule_edits}
    need_model = [i for i in items if i.id not in rule_covered or i.kind != "default"]
    if need_model and pages and not isinstance(model, NoModel):
        out = model.draft(_prompt(items, tk, (pr or {}).get("body"), pages, rule_edits))
        for e in out.get("edits", []):
            p = root / e.get("path", "")
            if not (p.is_file() and e.get("path") in pid):
                run["rejected"].append(f"{e.get('path')}: not an affected page")
                continue
            t = p.read_text()
            if t.count(e.get("find", "")) != 1 or not e.get("find"):
                run["rejected"].append(f"{e['path']}: anchor text not found exactly once")
                continue
            p.write_text(t.replace(e["find"], e["replace"], 1))
            run["edits"].append({"origin": "model", "path": e["path"], "line": t[:t.index(e["find"])].count("\n") + 1,
                                 "items": sorted({c for s in out.get("sentences", []) if norm(s["text"])[:40] in norm(e["replace"])
                                                  for c in s.get("sources", []) if c.startswith("C")}),
                                 "why": "drafted by the model"})
        source_map += [{"text": s["text"], "sources": s.get("sources", []), "origin": "model"} for s in out.get("sentences", [])]

    # Checks and revision loop.
    for attempt in range(MAX_REVISIONS + 1):
        g = check_grounding(repo, base_text, items, source_map, sources)
        failed = [s for s in g["sentences"] if s["status"] == "fail"]
        if not failed:
            break
        if attempt == MAX_REVISIONS or isinstance(model, NoModel):
            for s in failed:  # no unchecked fact reaches the writer
                q = f"[NEEDS INPUT: confirm and give a source for: {s['text'].rstrip('.')}]"
                if _replace_sentence(root, s["path"], s["text"], q):
                    source_map.append({"text": q, "sources": [], "origin": "placeholder"})
                    run["revised"].append(f"\"{s['text'][:80]}\" had no checked source ({s['reason']}); replaced with a question.")
            break
        run["revisions"] += 1
        fb = "\n".join(f"- \"{s['text']}\" ({s['path']} line {s['line']}): {s['reason']}" for s in failed)
        out = model.revise(_prompt(items, tk, (pr or {}).get("body"), pages, rule_edits, "## Failed sentences\n" + fb))
        for f in out.get("fixes", []):
            path = next((s["path"] for s in failed if norm(s["text"]) == norm(f.get("old", ""))), None)
            if path and _replace_sentence(root, path, f["old"], f["new"]):
                source_map.append({"text": f["new"], "sources": f.get("sources", []), "origin": "model revision"})
                run["revised"].append(f"\"{f['old'][:80]}\" revised to \"{f['new'][:80]}\".")

    # Coverage: every change item ends up in the draft, as text or as a question.
    g = check_grounding(repo, base_text, items, source_map, sources)
    for it in items:
        if g["coverage"].get(it.id):
            continue
        hit = next((h for h in hits if h["item"] == it.id and h["path"] != SUBS), None)
        path = hit["path"] if hit else (page_paths[0] if page_paths else "docs/nat/tune-nat-configuration.md")
        q = f"[NEEDS INPUT: {it.id} — {it.text} How should this page describe it?]"
        _insert_after_paragraph(root, path, hit["line"] if hit else 1, q)
        source_map.append({"text": q, "sources": [it.id], "origin": "placeholder"})
        run["edits"].append({"origin": "placeholder", "path": path, "line": hit["line"] if hit else 1,
                             "items": [it.id], "why": "no rule or sourced sentence covers this change item"})

    run.update(finish(repo, base_text, items, source_map, sources))
    run["source_map"] = source_map
    run["result"] = "draft"
    run["seconds"] = round(time.time() - t0, 1)
    run["tokens"] = getattr(model, "tokens", {"input": 0, "output": 0})
    return run


def finish(repo, base_text, items, source_map, sources, writer_ok=False):
    g = check_grounding(repo, base_text, items, source_map, sources)
    if writer_ok:
        for s in g["sentences"]:
            if s["status"] == "fail" and s.get("reason") == "no source map entry":
                s.update(status="writer", reason="writer-authored")
    st = check_style(repo, changed_lines(repo, base_text))
    b = check_build(repo)
    sc = score({**g, "sentences": [dict(s, status="pass" if s["status"] == "writer" else s["status"]) for s in g["sentences"]]}, st, b)
    b.pop("html", None)
    return {"grounding": g, "style": st, "build": b, "score": sc}


def row(run):
    """One run log row (design doc §5.6)."""
    sc = run.get("score", {})
    return {"run_id": run["run_id"], "type": run["type"], "started": run.get("started"), "head": run["head"],
            "model_id": run.get("model"), "prompt_version": run.get("prompt_version"),
            "vale_package": "Google", "change_types": ",".join(sorted({i["kind"] for i in run.get("items", [])})),
            "confidence": sc.get("total"), **{f"part_{k}": v for k, v in sc.get("parts", {}).items()},
            "revisions": run.get("revisions", 0), "placeholders": sc.get("questions", 0),
            "new_sentences": len(run.get("grounding", {}).get("sentences", [])),
            "tokens_in": run.get("tokens", {}).get("input", 0), "tokens_out": run.get("tokens", {}).get("output", 0),
            "seconds": run.get("seconds"), "result": run.get("result"), "docs_pr": run.get("docs_pr"),
            "edit_ratio": run.get("edit_ratio"), "final_confidence": run.get("final_confidence")}
