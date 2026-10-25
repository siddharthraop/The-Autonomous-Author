"""The three sample changes from the design doc's simulator (§6), run end to end."""
import pathlib
import shutil
import subprocess

import pytest

from author import model as M
from author.pipeline import draft
from author.report import render

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def sh(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    for d in ("product", "docs"):
        shutil.copytree(ROOT / d, r / d, ignore=shutil.ignore_patterns("_build", "__pycache__"))
    sh(r, "init", "-q", "-b", "main")
    sh(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "base", "--allow-empty")
    sh(r, "add", ".")
    sh(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    return r


def change(repo, old, new, msg="feature"):
    p = repo / "product/natctl/timeouts.py"
    s = p.read_text()
    assert old in s
    p.write_text(s.replace(old, new, 1))
    sh(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", msg)
    return "HEAD~1", "HEAD"


NEW_FIELD = ('    "udpIdleTimeoutSec",\n]', '    "udpIdleTimeoutSec",\n    "effectiveTcpTimeWaitTimeoutSec",\n]')
DEFAULT = ('"default": 120,', '"default": 30,')


def test_new_output_field(repo):
    base, head = change(repo, *NEW_FIELD)
    run = draft(repo, base, head, model=M.ScriptedModel(FIX / "new-field.json"))
    assert [i["kind"] for i in run["items"]] == ["field"]
    assert run["score"]["total"] == 10.0 and run["score"]["label"] == "ready for review"
    assert run["revisions"] == 0
    assert "effectiveTcpTimeWaitTimeoutSec" in (repo / "docs/nat/tune-nat-configuration.md").read_text()


def test_default_in_two_places_needs_no_model(repo):
    base, head = change(repo, *DEFAULT)
    run = draft(repo, base, head, model=M.NoModel())
    assert {e["origin"] for e in run["edits"]} == {"R-01", "R-03"}
    assert "nat_tcp_time_wait_default: 30 seconds" in (repo / "docs/substitutions.yml").read_text()
    assert "{{ nat_tcp_time_wait_default }}" in (repo / "docs/nat/troubleshooting.md").read_text()
    assert run["grounding"]["stale"] == []
    assert run["score"]["total"] == 10.0


def test_rollout_rule_becomes_a_question(repo):
    p = repo / "product/natctl/timeouts.py"
    s = p.read_text().replace('"default": 120,', '"default": 30,\n        "legacy_default": 120,', 1)
    s = s.replace(*NEW_FIELD)
    p.write_text(s)
    sh(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "Rollout\n\nDoc ticket: NAT-1182")
    run = draft(repo, "HEAD~1", "HEAD", model=M.ScriptedModel(FIX / "rollout.json"))
    kinds = [i["kind"] for i in run["items"]]
    assert kinds == ["default", "attribute", "field"]
    assert run["revisions"] == 1
    assert run["score"]["questions"] == 1
    assert run["score"]["label"] == "review closely" or run["score"]["total"] < 10
    text = (repo / "docs/nat/tune-nat-configuration.md").read_text()
    assert "1 November 2026" not in text and "[NEEDS INPUT:" in text
    assert all(s["status"] != "fail" for s in run["grounding"]["sentences"])
    assert "Where each sentence came from" in render(run)


def test_no_model_turns_new_field_into_a_question(repo):
    base, head = change(repo, *NEW_FIELD)
    run = draft(repo, base, head, model=M.NoModel())
    assert run["grounding"]["coverage"] == {"C1": True}
    assert run["score"]["questions"] == 1


def test_unrelated_change_needs_no_docs(repo):
    (repo / "product/natctl/__init__.py").write_text('"""natctl."""\n')
    sh(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "docstring")
    run = draft(repo, "HEAD~1", "HEAD")
    assert run["result"] == "no docs change"
