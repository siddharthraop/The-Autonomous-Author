"""The live demo behind the web app: a feature becomes a real commit in a sandbox
repository, the agent drafts the docs, and the result is compared with what a good
draft for that feature contains.

Nothing a visitor types is executed. A feature is a small set of edits to the sample
product's settings file, applied as text and validated first.
"""
import difflib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile

from markdown_it import MarkdownIt

from . import dita, model as models
from .change import Item
from .pages import SUBS, doc_files
from .pipeline import draft, finish
from .report import render
from .sentences import PLACEHOLDER

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = pathlib.Path(os.environ.get("AUTHOR_SAMPLE", ROOT / "sample"))
SETTINGS = "product/natctl/timeouts.py"
RUNS, LOCK = {}, threading.Lock()
TTL, MAX_RUNS = 3600, 25
REPORT_MD = MarkdownIt("commonmark", {"html": True}).enable("table")
NAME = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
FIELD = re.compile(r"^[a-z][A-Za-z0-9]{2,40}$")
SETTINGS_LIST = ["tcp_established", "tcp_transitory", "tcp_time_wait", "udp"]

SAMPLES = [
    {"id": "default", "title": "Lower the TCP TIME_WAIT default",
     "text": "Busy gateways run out of source ports because closed connections wait in TIME_WAIT for two minutes. "
             "This change lowers the default TCP TIME_WAIT timeout from 120 to 30 seconds. Operators can still set "
             "their own value with --tcp-time-wait-timeout.",
     "ops": [{"op": "set", "setting": "tcp_time_wait", "attr": "default", "value": 30}],
     "doc_type": "reference",
     "why": "A changed default. Fixed rules should do all of it, without the model: the value lives in one substitution, "
            "and a typed copy on another page must be found and fixed."},
    {"id": "field", "title": "Show the TIME_WAIT timeout in effect",
     "text": "After an override, operators can't tell which TIME_WAIT timeout a gateway is using. natctl describe now "
             "prints a new field, effectiveTcpTimeWaitTimeoutSec, with the value in effect.",
     "ops": [{"op": "field", "name": "effectiveTcpTimeWaitTimeoutSec"}],
     "doc_type": "task",
     "why": "A new output field. No rule can word this, so Gemini drafts one sentence on the page that documents "
            "natctl describe, and the checks confirm every fact in it."},
    {"id": "minimum", "title": "Reject UDP timeouts below 10 seconds",
     "text": "Very short UDP idle timeouts drop DNS replies. natctl update now rejects --udp-idle-timeout values "
             "below 10 seconds.",
     "ops": [{"op": "set", "setting": "udp", "attr": "minimum", "value": 10}],
     "doc_type": "reference",
     "why": "A new limit. The draft must state the minimum with its unit, and say nothing the change doesn't say, "
            "such as the exact error message."},
    {"id": "rollout", "title": "New default for new gateways only",
     "text": "Lower the TCP TIME_WAIT default to 30 seconds for new gateways. Existing gateways keep 120 seconds.",
     "ops": [{"op": "set", "setting": "tcp_time_wait", "attr": "default", "value": 30},
             {"op": "set", "setting": "tcp_time_wait", "attr": "legacy_default", "value": 120}],
     "doc_type": "reference",
     "why": "The hard case from the design document. The old value stays true for some gateways, so it must not be "
            "replaced everywhere, and anything the change doesn't say (when, which regions) must become a question."},
]
MONTHS = r"\b(January|February|March|April|May|June|July|August|September|October|November|December|20\d\d)\b"


# --- the feature as a commit -------------------------------------------------
def _block(src, setting):
    start = src.index(f'    "{setting}": {{')
    end = src.index("    },", start)
    return start, end


def apply_ops(src, ops):
    for o in ops:
        if o["op"] == "set":
            if o["setting"] not in SETTINGS_LIST or not NAME.match(o["attr"]) or o["attr"] in ("label", "unit", "flag", "field"):
                raise ValueError("unknown setting or attribute")
            v = int(o["value"])
            if not 1 <= v <= 86400:
                raise ValueError("values must be between 1 and 86400 seconds")
            start, end = _block(src, o["setting"])
            block = src[start:end]
            rx = re.compile(rf'(\n        "{o["attr"]}": )[^,\n]+,')
            block = rx.sub(rf"\g<1>{v},", block) if rx.search(block) else block + f'        "{o["attr"]}": {v},\n'
            src = src[:start] + block + src[end:]
        elif o["op"] == "field":
            if not FIELD.match(o["name"]) or f'"{o["name"]}"' in src:
                raise ValueError("field names are camelCase and new")
            src = src.replace('\n]\n', f'\n    "{o["name"]}",\n]\n', 1)
        elif o["op"] == "setting":
            if not NAME.match(o["name"]) or f'"{o["name"]}":' in src:
                raise ValueError("setting names are lower_case and new")
            label = re.sub(r"[^\w .-]", "", o.get("label") or o["name"].replace("_", " ").title())[:40]
            v = int(o["value"])
            camel = re.sub(r"_(\w)", lambda m: m.group(1).upper(), o["name"])
            block = (f'    "{o["name"]}": {{\n        "label": "{label}",\n        "default": {v},\n        "unit": "seconds",\n'
                     f'        "flag": "--{o["name"].replace("_", "-")}-idle-timeout",\n        "field": "{camel}IdleTimeoutSec",\n    }},\n')
            i = src.index("}\n\n# Fields printed")
            src = src[:i] + block + src[i:]
        else:
            raise ValueError("unknown change")
    return src


def _git(repo, *a, **kw):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True, **kw).stdout


def sandbox(ops, title, text, ticket_ref):
    d = pathlib.Path(tempfile.mkdtemp(prefix="author-demo-"))
    for sub in ("product", "docs"):
        shutil.copytree(SAMPLE / sub, d / sub, ignore=shutil.ignore_patterns("_build", "__pycache__"))
    if (ROOT / ".vale.ini").exists():
        shutil.copy(ROOT / ".vale.ini", d / ".vale.ini")
        if (ROOT / ".vale").exists():
            os.symlink(ROOT / ".vale", d / ".vale")
    me = ["-c", "user.name=natctl team", "-c", "user.email=team@example.com"]
    _git(d, "init", "-q", "-b", "main")
    _git(d, "add", "product", "docs")
    _git(d, *me, "commit", "-qm", "natctl 2.4 docs and code")
    p = d / SETTINGS
    p.write_text(apply_ops(p.read_text(), ops))
    msg = f"{title}\n\n{text}\n\nDoc ticket: {ticket_ref}"
    _git(d, "-c", "user.name=Developer", "-c", "user.email=developer@example.com", "commit", "-qam", msg)
    return d


# --- what a good draft contains ------------------------------------------------
def _new_sentences(run):
    return [s["text"] for s in run["grounding"]["sentences"]]


def expectations(sample_id, repo, run, dita_files, dita_errors):
    root = pathlib.Path(repo)
    page = lambda p: (root / p).read_text() if (root / p).exists() else ""
    subs, tune, trouble = page(SUBS), page("docs/nat/tune-nat-configuration.md"), page("docs/nat/troubleshooting.md")
    g, sc = run["grounding"], run["score"]
    fails = [s for s in g["sentences"] if s["status"] == "fail"]
    dmap = dita_files.get("dita/docs.ditamap", "")
    E = []

    def e(label, ok, detail=""):
        E.append({"label": label, "ok": bool(ok), "detail": detail})

    if sample_id in ("default", "rollout"):
        e("The new default is set once, in the substitution file", "nat_tcp_time_wait_default: 30 seconds" in subs,
          "rule R-01; every page that shows the default reads it from there")
        e("The DITA key nat-tcp-time-wait-default says 30 seconds", 'keys="nat-tcp-time-wait-default"><topicmeta><keywords><keyword>30 seconds' in dmap)
    if sample_id == "default":
        e("The typed copy of “120 seconds” on the troubleshooting page now uses the substitution",
          "{{ nat_tcp_time_wait_default }}" in trouble and "120 seconds" not in trouble, "rule R-03")
        e("No questions: every fact is in the change", sc["questions"] == 0)
        e("The model wasn't needed", not any(x["origin"] == "model" for x in run["edits"]), "fixed rules are cheaper and exact")
    if sample_id == "field":
        e("The new field is documented on the page about natctl describe", "effectiveTcpTimeWaitTimeoutSec" in tune)
        e("It appears in the DITA topic as <codeph>", "<codeph>effectiveTcpTimeWaitTimeoutSec</codeph>" in
          dita_files.get("dita/nat/tune-nat-configuration.dita", ""))
    if sample_id == "minimum":
        new = " ".join(_new_sentences(run))
        e("The minimum, 10 seconds, is stated with its unit, or asked as a question",
          re.search(r"\b10 seconds\b", new) or sc["questions"] > 0, new[:160])
        e("No invented error message", not re.search(r"error message|returns an error:", new, re.I))
    if sample_id == "rollout":
        e("120 seconds stays where it's still true for existing gateways", "120" in tune + trouble and not g["stale"])
        e("No invented rollout date or region", not re.search(MONTHS + r"|\bregions?\b", " ".join(_new_sentences(run))),
          "the change doesn't say when or where")
    e("Every new sentence has a checked source, or is a question for the developer", not fails,
      f"{len(fails)} unsourced" if fails else f"{len(g['sentences'])} sentence(s) checked")
    e("The docs build passes (Sphinx, warnings as errors)", run["build"]["build"])
    e("The DITA output is valid DITA 1.3", not dita_errors, "; ".join(dita_errors)[:200])
    return E


# --- runs ----------------------------------------------------------------------
def _prune():
    now = time.time()
    with LOCK:
        for k in [k for k, v in RUNS.items() if now - v["created"] > TTL] + list(RUNS)[:-MAX_RUNS]:
            v = RUNS.pop(k, None)
            if v:
                shutil.rmtree(v["repo"], ignore_errors=True)
                shutil.rmtree(v.get("html_dir") or "/nonexistent", ignore_errors=True)


def _diffs(repo, base_text, base_subs):
    root = pathlib.Path(repo)
    out = {}
    for path in doc_files(repo) + [SUBS]:
        a = base_subs if path == SUBS else base_text.get(path, "")
        b = (root / path).read_text()
        if a != b:
            out[path] = "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{path}", f"b/{path}", n=2))
    return out


def _result(st):
    run, repo = st["run"], st["repo"]
    files = dita.convert(repo)
    errors = dita.validate(files)
    st["dita"] = files
    qs = [{"question": s["question"], "path": s["path"], "line": s["line"]} for s in run["grounding"]["sentences"] if s["status"] == "question"]
    passed = run["build"]["build"] and not run["grounding"]["stale"] and not any(s["status"] == "fail" for s in run["grounding"]["sentences"])
    return {
        "run_id": st["id"], "sample": st["sample"], "status": st["status"],
        "commit": st["commit"], "code_diff": st["code_diff"],
        "items": run["items"], "score": run["score"], "model": run["model"], "model_error": run.get("model_error"),
        "report_html": REPORT_MD.render(render(run)), "questions": qs,
        "myst_diff": _diffs(repo, st["base_text"], st["base_subs"]),
        "dita_diff": dita.diff(st["dita_base"], files), "dita_errors": errors,
        "expected": expectations(st["sample"], repo, run, files, errors),
        "preview": [p.removeprefix("docs/").removesuffix(".md") + ".html" for p in _diffs(repo, st["base_text"], st["base_subs"]) if p.endswith(".md")],
        "can_approve": passed and not qs and st["status"] != "approved",
        "seconds": run.get("seconds"), "tokens": run.get("tokens"),
    }


def run_feature(spec, emit):
    """spec: {sample} or {title, text, ops}; plus optional doc_type and audience. emit(stage, detail) streams progress."""
    _prune()
    sample = next((s for s in SAMPLES if s["id"] == spec.get("sample")), None)
    title = (spec.get("title") or (sample or {}).get("title") or "").strip()[:100]
    text = (spec.get("text") or (sample or {}).get("text") or "").strip()[:1500]
    ops = spec.get("ops") or (sample or {}).get("ops")
    if not (title and text and ops):
        raise ValueError("a feature needs a title, a description and a change")
    rid = uuid.uuid4().hex[:10]
    ref = f"DOC-{rid[:4].upper()}"
    repo = sandbox(ops, title, text, ref)
    emit("commit", f"{_git(repo, 'rev-parse', '--short', 'HEAD').strip()} by Developer: {title}")
    root = pathlib.Path(repo)
    base_text = {p: (root / p).read_text() for p in doc_files(repo)}
    base_subs = (root / SUBS).read_text()
    dita_base = dita.convert(repo)
    doc_type = spec.get("doc_type") or (sample or {}).get("doc_type") or "reference"
    audience = (spec.get("audience") or "network operators")[:60]
    ticket = {"ref": ref, "system": "demo", "title": f"Docs: {title}", "doc_type": doc_type, "audience": audience,
              "text": f"Doc type: {doc_type}\nAudience: {audience}", "url": ""}
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    m = models.load("gemini" if key and spec.get("model", "gemini") == "gemini" else "none")
    run = draft(repo, "HEAD~1", "HEAD", model=m, pr={"number": None, "body": f"{title}\n\n{text}"},
                change_author="the developer", ticket_data=ticket, progress=emit)
    if run["result"] == "no docs change":
        shutil.rmtree(repo, ignore_errors=True)
        return {"run_id": rid, "status": "no docs change", "items": []}
    html = finish(repo, base_text, [Item(**i) for i in run["items"]], run["source_map"], run["sources"], keep_html=True)["html_dir"]
    emit("dita", "writing DITA 1.3 topics and map, validating against the OASIS DTDs")
    st = {"id": rid, "sample": (sample or {}).get("id", "custom"), "repo": str(repo), "run": run, "status": "in review",
          "base_text": base_text, "base_subs": base_subs, "dita_base": dita_base, "html_dir": html, "created": time.time(),
          "commit": {"sha": _git(repo, "rev-parse", "--short", "HEAD").strip(), "message": f"{title}\n\n{text}\n\nDoc ticket: {ref}",
                     "author": "Developer <developer@example.com>"},
          "code_diff": _git(repo, "diff", "HEAD~1", "HEAD", "--", "product/")}
    with LOCK:
        RUNS[rid] = st
    return _result(st)


def answer(rid, answers):
    """The writer answers the agent's questions; the checks run again on the edited draft."""
    st = RUNS.get(rid)
    if not st:
        raise KeyError(rid)
    run, root = st["run"], pathlib.Path(st["repo"])
    n = sum(1 for k in run["sources"] if k.startswith("W"))
    for q, a in answers.items():
        a = re.sub(r"[\[\]{}<>`]", "", (a or "")).strip()[:400]
        if not a:
            continue
        for path in doc_files(st["repo"]):
            p = root / path
            t = p.read_text()
            m = next((m for m in PLACEHOLDER.finditer(t) if m.group(1).strip() == q.strip()), None)
            if m:
                n += 1
                p.write_text(t[:m.start()] + a + t[m.end():])
                run["sources"][f"W{n}"] = a
                run["source_index"][f"W{n}"] = "the writer's answer in review"
                answered = re.findall(r"\bC\d+\b", q)  # the change items this question was about
                run["source_map"].append({"text": a, "sources": [f"W{n}", *answered], "origin": "writer"})
                break
    items = [Item(**i) for i in run["items"]]
    res = finish(st["repo"], st["base_text"], items, run["source_map"], run["sources"], writer_ok=True, keep_html=True)
    shutil.rmtree(st.get("html_dir") or "/nonexistent", ignore_errors=True)
    st["html_dir"] = res.pop("html_dir")
    run.update(res)
    run["revised"] = run.get("revised", []) + [f"The writer answered {len(answers)} question(s)."]
    return _result(st)


def approve(rid):
    st = RUNS.get(rid)
    if not st:
        raise KeyError(rid)
    res = _result(st)
    if not res["can_approve"]:
        raise ValueError("answer every question and pass every check before approving")
    st["status"] = "approved"
    return _result(st)


def bundle(rid):
    st = RUNS.get(rid)
    if not st:
        raise KeyError(rid)
    res = _result(st)
    buf = io.BytesIO()
    root = pathlib.Path(st["repo"])
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in doc_files(st["repo"]) + [SUBS, "docs/conf.py"]:
            z.write(root / p, f"myst/{p}")
        for p, t in st["dita"].items():
            z.writestr(p, t)
        z.writestr("report.md", render(st["run"]))
        z.writestr("code.diff", st["code_diff"])
        z.writestr("myst.diff", "".join(res["myst_diff"].values()))
        z.writestr("dita.diff", "".join(res["dita_diff"].values()))
        z.writestr("README.md", f"# Docs draft {rid}\n\nStatus: {st['status']}. Confidence {res['score']['total']} / 10.\n\n"
                   "- `myst/`: the docs-as-code source with the draft applied\n- `dita/`: the same docs as DITA 1.3 topics and a map\n"
                   "- `report.md`: the explainability report\n- `*.diff`: what changed\n")
    return buf.getvalue()


def preview(rid, path):
    st = RUNS.get(rid)
    if not st or not st.get("html_dir"):
        raise KeyError(rid)
    base = pathlib.Path(st["html_dir"]).resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise KeyError(path)
    return f
