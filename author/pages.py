"""Tool 2, find_pages: find every page and line that a change item reaches."""
import pathlib
import re

DOCS = "docs"
SUBS = "docs/substitutions.yml"


def doc_files(repo):
    root = pathlib.Path(repo) / DOCS
    return sorted(str(p.relative_to(repo)) for p in root.rglob("*.md") if "_build" not in p.parts)


def term(item):
    """A short word that names the setting in prose, such as TIME_WAIT or established."""
    name = item.name[4:] if item.name.startswith("tcp_") else item.name
    return name.replace("_", "[_ ]")


def old_value_re(item):
    return re.compile(rf"\b{re.escape(str(item.old))}\s*(?:{re.escape(item.unit)}|s\b)", re.I) if item.old is not None else None


def find_pages(repo, items, scope=None):
    """Return hits: page, line number, item ID and match type. `scope` is the ticket's page list."""
    hits = []
    files = doc_files(repo)
    for path in files + [SUBS]:
        lines = (pathlib.Path(repo) / path).read_text().splitlines()
        for n, line in enumerate(lines, 1):
            for it in items:
                why = None
                if it.key and re.match(rf"\s*{it.key}\s*:", line):
                    why = "substitution"
                elif it.key and "{{ " + it.key + " }}" in line:
                    why = "substitution reference"
                elif it.flag and it.flag in line:
                    why = "flag"
                elif it.field and it.field in line:
                    why = "field"
                elif it.kind == "field" and "natctl describe" in line:
                    why = "describe command"
                elif (rx := old_value_re(it)) and rx.search(line) and re.search(term(it), line, re.I):
                    why = "old value"
                if why:
                    hits.append({"path": path, "line": n, "item": it.id, "match": why, "text": line.strip()})
    for p in scope or []:
        cand = p if p.startswith(DOCS) else f"{DOCS}/{p}"
        cand = cand if cand.endswith(".md") else cand + ".md"
        if cand in files and not any(h["path"] == cand for h in hits):
            hits.append({"path": cand, "line": 1, "item": "T1", "match": "doc ticket scope", "text": ""})
    return hits
