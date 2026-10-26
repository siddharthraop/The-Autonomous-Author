"""Tool 7, part two: the explainability report (design doc §5.5 and Figure 13)."""

BADGE = {"ready for review": "🟢", "review closely": "🟠", "needs writer": "🔴"}
MARK = "<!-- autonomous-author:report -->"


def render(run):
    sc, g = run["score"], run["grounding"]
    sents = g["sentences"]
    L = [MARK, f"## Autonomous Author draft · confidence {sc['total']} / 10 · {BADGE[sc['label']]} {sc['label']}", ""]
    L.append(f"Code change `{run['base'][:7]}..{run['head'][:7]}`"
             + (f" · code PR #{run['code_pr']}" if run.get("code_pr") else "")
             + (f" · doc ticket [{run['ticket']['ref']}]({run['ticket'].get('url', '')})" if run.get("ticket") else " · no doc ticket linked")
             + f" · model `{run['model']}` · prompt `{run['prompt_version']}` · run `{run['run_id']}`")
    L += ["", "| Changes | Sentences | Sourced | Revised | Questions |", "| --- | --- | --- | --- | --- |",
          f"| {len(run['items'])} | {len(sents)} | {sum(s['status'] == 'pass' for s in sents)} | {run['revisions']} | {sc['questions']} |", ""]
    L += ["### What changed", ""] + [f"- `{i['id']}` {i['text']} (`{i['path']}` line {i['line']})" for i in run["items"]]
    L += ["", "### Sources", ""] + [f"- `{k}` {v}" for k, v in run["source_index"].items()]
    L += ["", "### What the agent edited and why", ""]
    for e in run["edits"]:
        L.append(f"- {e['origin']} · `{e['path']}`" + (f" line {e['line']}" if e.get("line") else "")
                 + f" for {', '.join(e['items']) or 'scope'}: {e['why']}")
    if not run["edits"]:
        L.append("- No edits.")
    if run.get("dita"):
        d = run["dita"]
        L += ["", "### DITA", "",
              (f"The same draft as DITA 1.3, in `dita/`: {', '.join(f'`{c}`' for c in d['changed']) or 'no DITA change'}. "
               + ("✅ Valid against the OASIS DITA 1.3 DTDs." if not d["errors"] else f"❌ Not valid: {'; '.join(d['errors'])[:300]}")),
              "Values are `<keyword keyref>` keys defined in `dita/docs.ditamap`; questions are `<draft-comment>` elements."]
    L += ["", "### Where each sentence came from", "", "| Sentence | Source | Check |", "| --- | --- | --- |"]
    for s in sents:
        chk = {"pass": f"✅ literals {s.get('literals', '0/0')}", "question": "❓ question"}.get(s["status"], f"❌ {s.get('reason', '')}")
        L.append(f"| {s['text'].replace('|', '¦')[:160]} | {', '.join(s.get('sources', [])) or 'none'} | {chk} |")
    L += ["", "### Check these", ""]
    checks = []
    for s in sents:
        if s["status"] == "question":
            checks.append(f"- ❓ {s['question']} — asked of {run.get('change_author') or 'the change author'}.")
        elif s["status"] == "fail":
            checks.append(f"- ❌ `{s['path']}` line {s['line']}: {s['reason']}.")
    if run.get("model_error"):
        checks.append(f"- ⚠️ The model call failed, so rules and questions made this draft: `{run['model_error'][:200]}`")
    checks += [f"- 🔁 Revised: {r}" for r in run["revised"]]
    checks += [f"- ⚠️ Stale value left: `{x['path']}` line {x['line']}: {x['text']}" for x in g["stale"]]
    checks += [f"- ⚠️ Not covered: `{k}`" for k, v in g["coverage"].items() if not v]
    st = run["style"]
    if not st["ran"]:
        checks.append("- ⚠️ Vale did not run; style is not checked.")
    checks += [f"- ✏️ Style {a['severity']}: `{a['path']}` line {a['line']} {a['rule']}: {a['message']}" for a in st["alerts"]]
    if run.get("dita", {}).get("errors"):
        checks.append("- ❌ The DITA output isn't valid DITA 1.3.")
    if run.get("dita", {}).get("out_of_sync"):
        checks.append(f"- ❌ `dita/` doesn't match `docs/`: {', '.join(run['dita']['out_of_sync'])}. Run `author dita`.")
    b = run["build"]
    if not b["build"]:
        checks.append("- ❌ Sphinx build failed (warnings are errors).")
    checks += [f"- 🔗 Broken link: {u}" for u in b["broken"]]
    if not b.get("links_ran"):
        checks.append("- ⚠️ lychee did not run; links are not checked.")
    checks += [f"- ⚠️ Edit not applied: {r}" for r in run.get("rejected", [])]
    L += checks or ["- Nothing flagged. Check wording and structure."]
    p = sc["parts"]
    L += ["", "<details><summary>Score breakdown</summary>", "",
          f"grounding {p['grounding']} + coverage {p['coverage']} + stale values {p['stale']} + style {p['style']}"
          f" + build and links {p['build']} − questions {sc['penalty']} = **{sc['total']}**", "", "</details>", "",
          "The checks compute this score, not the model. A writer must approve this pull request; the agent cannot merge it."]
    return "\n".join(L)
