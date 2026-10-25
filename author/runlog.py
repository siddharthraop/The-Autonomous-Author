"""The run log: one row per run (design doc §5.6).

Rows go to BigQuery when AUTHOR_BQ_TABLE is set (project.dataset.table), and always
to the `runlog` branch as JSON lines, so the drift check works with no cloud setup.
"""
import json
import os
import pathlib
import subprocess
import tempfile

BRANCH = "runlog"
FILE = "runs.jsonl"


def _git(cwd, *a, check=True):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=check)


def append(repo, row, push=True):
    out = pathlib.Path(repo) / ".author" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "row.json").write_text(json.dumps(row))
    table = os.environ.get("AUTHOR_BQ_TABLE")
    if table:
        r = subprocess.run(["bq", "insert", table, str(out / "row.json")], capture_output=True, text=True)
        print("bigquery:", "ok" if r.returncode == 0 else r.stderr.strip()[:300])
    if not push:
        return
    wt = tempfile.mkdtemp(prefix="runlog-")
    for attempt in range(3):
        has = _git(repo, "ls-remote", "--exit-code", "--heads", "origin", BRANCH, check=False).returncode == 0
        if has:
            _git(repo, "fetch", "-q", "origin", f"{BRANCH}:refs/remotes/origin/{BRANCH}")
            _git(repo, "worktree", "add", "-f", "-B", BRANCH, wt, f"origin/{BRANCH}")
        else:
            _git(repo, "worktree", "add", "-f", "--orphan", "-b", BRANCH, wt)
        with open(pathlib.Path(wt) / FILE, "a") as f:
            f.write(json.dumps(row) + "\n")
        _git(wt, "add", FILE)
        _git(wt, "-c", "user.name=Autonomous Author", "-c", "user.email=autonomous-author@users.noreply.github.com",
             "commit", "-qm", f"Run log: {row['type']} {row['run_id']}")
        ok = _git(wt, "push", "-q", "origin", f"HEAD:{BRANCH}", check=False).returncode == 0
        _git(repo, "worktree", "remove", "--force", wt, check=False)
        if ok:
            return
    print("run log: push failed after 3 attempts; row kept in .author/out/row.json")


def read(repo):
    if _git(repo, "fetch", "-q", "origin", f"{BRANCH}:refs/remotes/origin/{BRANCH}", check=False).returncode != 0:
        return []
    r = _git(repo, "show", f"origin/{BRANCH}:{FILE}", check=False)
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
