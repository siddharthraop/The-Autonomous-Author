"""Command line: `author draft | check | review | drift`. The workflows call these."""
import argparse
import json
import os
import pathlib
import subprocess
import sys

from . import drift as drift_mod, model as models, review as review_mod, runlog
from .change import Item
from .github import GitHub
from .gitio import git, resolve, show
from .pages import doc_files
from .pipeline import draft, finish, row
from .report import MARK, render

AGENT = ["-c", "user.name=Autonomous Author", "-c", f"user.email={review_mod.AGENT_EMAIL}"]
OUT = pathlib.Path(".author/out")


def _output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.writelines(f"{k}={v}\n" for k, v in kw.items())


def _run_url():
    s, r, i = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{s}/{r}/actions/runs/{i}" if s and r and i else None


def cmd_draft(a):
    repo = "."
    head = resolve(repo, a.head)
    base = a.base
    if not base or set(base) == {"0"} or subprocess.run(["git", "cat-file", "-e", base + "^{commit}"]).returncode:
        base = resolve(repo, head + "~1")
    gh = GitHub()
    pr = None
    if gh.enabled:
        pr = next((p for p in gh.pulls_for_commit(head) if p.get("merged_at")), None)
    author = (pr or {}).get("user", {}).get("login") or os.environ.get("GITHUB_ACTOR")
    spec = a.model
    if spec == "auto":
        spec = "gemini" if (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")) else "none"
    run = draft(repo, base, head, model=models.load(spec), pr=pr, change_author=author, gh=gh, ticket_file=a.ticket_file)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run.json").write_text(json.dumps(run, indent=1, default=str))
    if run["result"] == "no docs change":
        print("No reader-visible change items: no docs change.")
        if a.publish and gh.enabled:
            gh.commit_comment(head, "Autonomous Author: no reader-visible change items in this change, so no docs change.")
            runlog.append(repo, row(run))
        _output(result="none")
        return 0
    report = render(run)
    (OUT / "report.md").write_text(report)
    print(report)
    if not a.publish:
        return 0
    branch = f"author/{head[:7]}"
    drafts = pathlib.Path(".author/drafts")
    drafts.mkdir(parents=True, exist_ok=True)
    keep = {k: run[k] for k in ("run_id", "base", "head", "items", "source_map", "source_index", "model", "prompt_version")}
    keep["sources"] = run["sources"]
    (drafts / f"{run['run_id']}.json").write_text(json.dumps(keep, indent=1, default=str))
    git(repo, "checkout", "-q", "-B", branch)
    touched = sorted({e["path"] for e in run["edits"]})  # stage only what the agent edited
    git(repo, "add", "--", *touched, str(drafts / f"{run['run_id']}.json"))
    subject = git(repo, "log", "-1", "--format=%s", head).strip()
    git(repo, *AGENT, "commit", "-q", "-m", f"Docs draft for {head[:7]}: {subject}\n\nRun {run['run_id']}. Confidence {run['score']['total']} / 10.")
    git(repo, "push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}")
    sha = resolve(repo, "HEAD")
    _output(result="draft", branch=branch, sha=sha)
    if not gh.enabled:
        print(f"Pushed {branch}. No GITHUB_TOKEN, so no pull request was opened.")
        return 0
    sc = run["score"]
    tk = run.get("ticket")
    body = "\n".join([
        f"First draft of the docs for code change {head[:7]} ({subject}).",
        "",
        f"- Confidence: **{sc['total']} / 10, {sc['label']}**. The full explainability report is the first comment.",
        f"- Code PR: #{run['code_pr']}" if run.get("code_pr") else f"- Code commit: {head}",
        f"- Doc ticket: {tk['ref']}" if tk else "- Doc ticket: none linked. Add `Doc ticket: #N` to the code PR or commit message.",
        f"- Questions: {sc['questions']}, asked in a comment below.",
        "",
        "A writer reviews and approves this pull request. The agent cannot merge it.",
        f"<!-- autonomous-author run={run['run_id']} head={head} -->"])
    try:
        created = gh.open_pr(branch, a.target, f"Docs draft: {subject}", body, draft=True)
    except Exception as e:
        detail = getattr(e, "read", lambda: b"")().decode()[:300]
        print(f"::error title=Draft pull request not opened::{e} {detail} Branch {branch} is pushed. "
              "If this is a 403, turn on Settings > Actions > General > Workflow permissions > "
              "'Allow GitHub Actions to create and approve pull requests', then re-run.")
        runlog.append(repo, row({**run, "result": "branch only"}))
        return 1
    num = created["number"]
    gh.comment(num, report)
    band = {"ready for review": "ready-for-review", "review closely": "review-closely", "needs writer": "needs-writer"}[sc["label"]]
    gh.labels(num, ["autonomous-author", band])
    qs = [s["question"] for s in run["grounding"]["sentences"] if s["status"] == "question"]
    if qs:
        who = f"@{author}" if author else "change author"
        gh.comment(num, f"{who}, the draft needs your input on {len(qs)} point(s). Reply here; the writer updates the draft.\n\n"
                   + "\n".join(f"{n}. {q}" for n, q in enumerate(qs, 1)))
    _post_ticket(gh, tk, created["html_url"], sc)
    gh.status(sha, "success" if sc["label"] != "needs writer" else "failure", "autonomous-author/confidence",
              f"{sc['total']} / 10 · {sc['label']}", _run_url())
    run["docs_pr"] = num
    runlog.append(repo, row(run))
    _output(result="draft", branch=branch, pr=num, sha=sha)
    print(f"Opened draft docs PR #{num}: {created['html_url']}")
    return 0


def _post_ticket(gh, tk, url, sc):
    if not tk:
        return
    msg = f"Autonomous Author opened a draft docs pull request: {url}\nConfidence {sc['total']} / 10, {sc['label']}. Moved to review."
    try:
        if tk["system"] == "github":
            gh.comment(tk["number"], msg)
            gh.labels(tk["number"], ["docs-review"])
        elif tk["system"] == "jira":
            import base64
            import urllib.request
            b = os.environ["JIRA_BASE_URL"].rstrip("/")
            req = urllib.request.Request(f"{b}/rest/api/3/issue/{tk['ref']}/comment", method="POST", data=json.dumps(
                {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": msg}]}]}}).encode())
            req.add_header("Authorization", "Basic " + base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode())
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=30)
    except Exception as e:  # the draft still stands if the ticket update fails
        print(f"doc ticket update failed: {e}")


def _check_run(repo, base_ref):
    mb = git(repo, "merge-base", base_ref, "HEAD").strip()
    base_text = {p: show(repo, mb, p) or "" for p in doc_files(repo)}
    items, smap, sources, index, meta = [], [], {}, {}, {}
    for f in git(repo, "diff", "--name-only", mb, "HEAD", "--", ".author/drafts").split():
        if pathlib.Path(f).exists():
            d = json.loads(pathlib.Path(f).read_text())
            items += [Item(**i) for i in d["items"]]
            smap += d["source_map"]
            sources.update(d["sources"])
            index.update(d["source_index"])
            meta = d
    res = finish(repo, base_text, items, smap, sources, writer_ok=True)
    run = {"run_id": meta.get("run_id", "check"), "base": mb, "head": resolve(repo, "HEAD"), "model": meta.get("model", "n/a"),
           "prompt_version": meta.get("prompt_version", "n/a"), "items": [i.to_dict() for i in items],
           "source_index": index, "edits": [], "revisions": 0, "revised": [], **res}
    return run


def cmd_check(a):
    run = _check_run(".", a.base)
    g = run["grounding"]
    problems = [s for s in g["sentences"] if s["status"] == "fail"]
    ok = run["build"]["build"] and not problems and not g["stale"] and run["style"]["errors"] == 0 \
        and run["build"]["links_ok"] and run["style"]["ran"]
    text = render(run).replace(MARK, "<!-- autonomous-author:docs-checks -->").replace("Autonomous Author draft", "docs-checks")
    writer = [s for s in g["sentences"] if s["status"] == "writer"]
    if writer:
        text += f"\n\n✍️ {len(writer)} sentence(s) are writer-authored and have no source map entry; the writer is their source."
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "checks.md").write_text(text)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")
    gh = GitHub()
    if a.status and gh.enabled:
        gh.status(a.sha or run["head"], "success" if ok else "failure", "docs-checks",
                  f"{'pass' if ok else 'fail'} · confidence {run['score']['total']} / 10", _run_url())
    return 0 if ok else 1


def cmd_review(a):
    ev = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text()) if a.event is None else json.loads(pathlib.Path(a.event).read_text())
    pr = ev["pull_request"]
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    mb = git(".", "merge-base", base, head).strip()
    d_sha = review_mod.agent_commit(".", mb, head)
    if not d_sha:
        print("No agent commit on this branch.")
        return 0
    final = pr.get("merge_commit_sha") if pr.get("merged") else head
    ratio = review_mod.edit_ratio(".", mb, d_sha, head)
    swaps = review_mod.word_swaps(".", d_sha, head)
    run = _check_run(".", mb) if pr.get("merged") else None
    rowd = {"run_id": pr["head"]["ref"].split("/")[-1] + f"-review-{pr['number']}", "type": "review", "head": final,
            "docs_pr": pr["number"], "result": "merged" if pr.get("merged") else "closed", "edit_ratio": ratio,
            "final_confidence": run["score"]["total"] if run else None, "swaps": swaps}
    print(json.dumps(rowd))
    runlog.append(".", rowd)
    gh = GitHub()
    rules = review_mod.proposed_rules(runlog.read("."))
    if rules and gh.enabled and not gh.search_open_issues("vale-rule"):
        gh.open_issue("Proposed Vale rule from repeated writer edits",
                      "Writers made the same word replacement in at least 3 reviewed drafts. A writer approves this rule "
                      "by adding it to `.vale/styles/config/Author/Swaps.yml`.\n\n```yaml\n" + review_mod.vale_rule(rules) + "```",
                      ["vale-rule"])
    return 0


def cmd_drift(a):
    rows = runlog.read(".")
    res = drift_mod.check(rows)
    print(json.dumps(res, indent=1))
    gh = GitHub()
    if res["findings"] and gh.enabled and not gh.search_open_issues("drift"):
        body = f"Baseline mean {res['baseline_mean']}, last 10 runs {res['recent_mean']}.\n\n" + \
               "\n".join(f"- **{k}**: {v}" for k, v in res["findings"]) + "\n\nRuns: " + ", ".join(f"`{r}`" for r in res["runs"])
        gh.open_issue(f"Drift: {res['findings'][0][0]}", body, ["drift"])
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="author")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft", help="draft docs for a code change")
    d.add_argument("--base"), d.add_argument("--head", default="HEAD")
    d.add_argument("--model", default="auto", help="auto | gemini | none | scripted:<file>")
    d.add_argument("--ticket-file"), d.add_argument("--target", default="main")
    d.add_argument("--publish", action="store_true", help="push a branch and open the draft PR")
    c = sub.add_parser("check", help="docs-checks for the current branch")
    c.add_argument("--base", default="origin/main"), c.add_argument("--status", action="store_true"), c.add_argument("--sha")
    r = sub.add_parser("review", help="record a closed docs PR")
    r.add_argument("--event")
    sub.add_parser("drift", help="daily drift check")
    a = p.parse_args(argv)
    return {"draft": cmd_draft, "check": cmd_check, "review": cmd_review, "drift": cmd_drift}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
