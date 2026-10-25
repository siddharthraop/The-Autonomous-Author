"""Fixed rules. They make edits that need no wording, so the model is not called for them.

R-01  A changed default updates its MyST substitution once.
R-03  A typed copy of a replaced default becomes a reference to its substitution.
"""
import pathlib
import re

from .pages import SUBS, doc_files, old_value_re, term


def apply_rules(repo, items):
    edits = []
    root = pathlib.Path(repo)
    subs = root / SUBS
    for it in [i for i in items if i.kind == "default"]:
        text = subs.read_text()
        rx = re.compile(rf"^(\s*{it.key}\s*:\s*)(.*)$", re.M)
        m = rx.search(text)
        new_val = f"{it.new} {it.unit}".strip()
        if m and m.group(2).strip() != new_val:
            subs.write_text(text[:m.start(2)] + new_val + text[m.end(2):])
            edits.append({"rule": "R-01", "item": it.id, "path": SUBS, "before": m.group(0).strip(),
                          "after": f"{it.key}: {new_val}"})
        elif not m:
            with subs.open("a") as f:
                f.write(f"{it.key}: {new_val}\n")
            edits.append({"rule": "R-01", "item": it.id, "path": SUBS, "before": "", "after": f"{it.key}: {new_val}"})
        vrx = old_value_re(it)
        if any(i.name == it.name and i.kind == "attribute" and i.new == it.old for i in items):
            continue  # the old value is still true for some readers; the model or a person words it
        for path in doc_files(repo):
            p = root / path
            lines = p.read_text().splitlines(keepends=True)
            changed = False
            for n, line in enumerate(lines):
                if "{{" not in line and vrx.search(line) and re.search(term(it), line, re.I):
                    lines[n] = vrx.sub("{{ " + it.key + " }}", line)
                    edits.append({"rule": "R-03", "item": it.id, "path": path, "line": n + 1,
                                  "before": line.strip(), "after": lines[n].strip()})
                    changed = True
            if changed:
                p.write_text("".join(lines))
    return edits
