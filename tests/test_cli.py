"""End to end through the command line: commit a feature, get a draft branch, then docs-checks pass on it."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(cwd, *a, check=True):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GITHUB_TOKEN": "", "GITHUB_REPOSITORY": ""}
    return subprocess.run(list(a), cwd=cwd, capture_output=True, text=True, check=check, env=env)


def test_commit_feature_gets_draft_and_checks_pass(tmp_path):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    run(tmp_path, "git", "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    for d in ("product", "docs"):
        shutil.copytree(ROOT / "tests/fixtures/base" / d, work / d)
    if (ROOT / ".vale").exists():
        shutil.copytree(ROOT / ".vale", work / ".vale")
    shutil.copy(ROOT / ".vale.ini", work)
    g = lambda *a: run(work, "git", "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a)
    g("init", "-q", "-b", "main"), g("remote", "add", "origin", str(remote)), g("add", "."), g("commit", "-qm", "base")
    g("push", "-q", "origin", "main")
    p = work / "product/natctl/timeouts.py"
    p.write_text(p.read_text().replace('"default": 120,', '"default": 30,', 1))
    g("commit", "-qam", "Lower the TIME_WAIT default")
    g("push", "-q", "origin", "main")
    out = run(work, sys.executable, "-m", "author", "draft", "--base", "HEAD~1", "--model", "none", "--publish")
    assert "Pushed author/" in out.stdout, out.stdout + out.stderr
    branch = next(l.split()[1].rstrip(".") for l in out.stdout.splitlines() if l.startswith("Pushed "))
    assert run(work, "git", "ls-remote", str(remote), branch).stdout
    log = run(work, "git", "log", "-1", "--format=%an <%ae>").stdout
    assert log.startswith("Autonomous Author")
    g("fetch", "-q", "origin")
    chk = run(work, sys.executable, "-m", "author", "check", "--base", "origin/main", check=False)
    assert chk.returncode == 0, chk.stdout + chk.stderr
    assert "confidence 10.0" in chk.stdout
