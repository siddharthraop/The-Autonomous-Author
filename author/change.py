"""Tool 1, read_change: turn a code change into reader-visible change items.

The parser reads the product's settings module at the base and head revisions
and compares the values, so a change item is a fact taken from the code, not a
guess. Each item gets an ID (C1, C2 ...) and keeps its old and new value.
"""
import ast
import re
from dataclasses import dataclass, asdict, field as dc_field

from .gitio import git, show

SETTINGS = "product/natctl/timeouts.py"
KNOWN = {"label", "default", "unit", "flag", "field"}


@dataclass
class Item:
    id: str
    kind: str            # default | new_setting | flag | field | attribute
    name: str
    text: str            # one plain sentence a reader could check
    old: object = None
    new: object = None
    unit: str = ""
    label: str = ""
    flag: str = ""
    field: str = ""
    key: str = ""        # MyST substitution key for a default value
    path: str = SETTINGS
    line: int = 0
    attribute: str = ""
    evidence: list = dc_field(default_factory=list)  # diff lines for this item

    def source_text(self):
        return " ".join([self.text, self.label, self.flag, self.field, str(self.old), str(self.new),
                         self.unit, *self.evidence])

    def to_dict(self):
        return asdict(self)


def _literals(src):
    out = {}
    if not src:
        return out
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def _line_of(src, needle):
    for i, line in enumerate((src or "").splitlines(), 1):
        if needle in line:
            return i
    return 0


def read_change(repo, base, head):
    """Return (items, diff_text) for the change between two revisions."""
    old_src, new_src = show(repo, base, SETTINGS), show(repo, head, SETTINGS)
    diff = git(repo, "diff", "--unified=2", base, head, "--", "product/")
    if new_src is None or old_src is None:
        return [], diff  # removed, or first import: nothing a reader saw has changed
    old, new = _literals(old_src), _literals(new_src)
    o_t, n_t = old.get("TIMEOUTS", {}), new.get("TIMEOUTS", {})
    added = [l[1:].strip() for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    items = []

    def add(kind, name, text, **kw):
        ev = [l for l in added if any(str(v) and str(v) in l for v in (name, kw.get("field"), kw.get("flag"), kw.get("attribute")) if v)]
        items.append(Item(id=f"C{len(items) + 1}", kind=kind, name=name, text=text, evidence=ev[:6], **kw))

    for name, t in n_t.items():
        base_kw = dict(unit=t.get("unit", ""), label=t.get("label", name), flag=t.get("flag", ""),
                       field=t.get("field", ""), key=f"nat_{name}_default",
                       line=_line_of(new_src, f'"{name}"'))
        if name not in o_t:
            add("new_setting", name, f"New setting {t.get('label', name)}: default {t.get('default')} {t.get('unit', '')}, "
                f"flag {t.get('flag')}, field {t.get('field')}.", new=t.get("default"), **base_kw)
            continue
        p = o_t[name]
        if p.get("default") != t.get("default"):
            add("default", name, f"{t['label']} default changed from {p.get('default')} to {t.get('default')} {t.get('unit', '')}.",
                old=p.get("default"), new=t.get("default"), **base_kw)
        if p.get("flag") != t.get("flag"):
            add("flag", name, f"{t['label']} flag changed from {p.get('flag')} to {t.get('flag')}.",
                old=p.get("flag"), new=t.get("flag"), **base_kw)
        for attr in sorted((set(p) | set(t)) - KNOWN):
            if p.get(attr) != t.get(attr):
                unit = f" {t.get('unit')}" if isinstance(t.get(attr), (int, float)) and t.get("unit") else ""
                was = "not set" if p.get(attr) is None else f"{p.get(attr)}{unit}"
                add("attribute", name, f"{t['label']}: {attr} changed from {was} to {t.get(attr)}{unit}.",
                    old=p.get(attr), new=t.get(attr), attribute=attr, **base_kw)
    old_f, new_f = old.get("DESCRIBE_FIELDS", []), new.get("DESCRIBE_FIELDS", [])
    for f in new_f:
        if f not in old_f:
            add("field", f, f"New output field {f} in natctl describe.", new=f, field=f,
                line=_line_of(new_src, f'"{f}"'))
    return items, diff


def commit_messages(repo, base, head):
    return git(repo, "log", "--format=%B", f"{base}..{head}")


TICKET_RE = re.compile(r"Doc ticket:\s*(#\d+|[A-Z][A-Z0-9]+-\d+)", re.I)


def ticket_ref(text):
    m = TICKET_RE.search(text or "")
    return m.group(1) if m else None
