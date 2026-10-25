"""Tool 8, record_review: learn from what the writer kept and changed (design doc §5.3)."""
import collections
import difflib
import json
import re

from .gitio import git, show

AGENT_EMAIL = "autonomous-author@users.noreply.github.com"


def _added(repo, a, b):
    d = git(repo, "diff", "--unified=0", a, b, "--", "docs/")
    return "\n".join(l[1:] for l in d.splitlines() if l.startswith("+") and not l.startswith("+++"))


def edit_ratio(repo, base, draft_sha, final_sha):
    """Share of the agent's draft that the writer changed: 0 kept as is, 1 fully rewritten."""
    a, b = _added(repo, base, draft_sha), _added(repo, base, final_sha)
    if not a:
        return 0.0
    return round(1 - difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio(), 3)


def word_swaps(repo, draft_sha, final_sha):
    """Single-word replacements the writer made, for example 'utilize' -> 'use'."""
    a, b = re.findall(r"\w+", _added(repo, draft_sha + "~1", draft_sha)), re.findall(r"\w+", _added(repo, draft_sha + "~1", final_sha))
    swaps = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "replace" and i2 - i1 == 1 and j2 - j1 == 1 and a[i1].lower() != b[j1].lower():
            swaps.append([a[i1].lower(), b[j1].lower()])
    return swaps


def agent_commit(repo, base, head):
    """The agent's draft commit on the branch: the newest commit authored by the agent."""
    for line in git(repo, "log", "--format=%H %ae", f"{base}..{head}").splitlines():
        sha, email = line.split()
        if email == AGENT_EMAIL:
            return sha
    return None


def proposed_rules(rows, minimum=3):
    """A word the writer replaced the same way in `minimum` reviews becomes a proposed Vale rule."""
    counts = collections.Counter(tuple(s) for r in rows if r.get("type") == "review" for s in r.get("swaps") or [])
    return [(a, b, n) for (a, b), n in counts.items() if n >= minimum]


def vale_rule(swaps):
    lines = ["extends: substitution", "message: \"Use '%s' instead of '%s'.\"", "level: warning", "ignorecase: true", "swap:"]
    lines += [f"  {a}: {b}" for a, b, _ in swaps]
    return "\n".join(lines) + "\n"
