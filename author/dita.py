"""Deliver the docs as DITA 1.3 as well as MyST: one source, two outputs.

The agent edits the MyST source, where the checks run. This module writes the
same pages as DITA topics and a map, so a DITA team reviews the draft in DITA:
  {{ key }}            -> <keyword keyref="key"/> (keys defined in the map, from substitutions.yml)
  [NEEDS INPUT: q]     -> <draft-comment author="autonomous-author" disposition="open">
  `code`               -> <codeph>,  ```lang -> <codeblock outputclass="language-lang">
  tables               -> <simpletable>,  links to .md -> <xref href="*.dita">
The output is validated against the OASIS DITA 1.3 DTDs.
"""
import difflib
import html
import os
import pathlib
import re

import yaml
from markdown_it import MarkdownIt

from .sentences import PLACEHOLDER

VENDOR = pathlib.Path(os.environ.get("AUTHOR_DITA_DTD", pathlib.Path(__file__).resolve().parents[1] / "vendor" / "dita13"))
TOPIC_DT = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
MAP_DT = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
SUB = re.compile(r"\{\{\s*([\w-]+)\s*\}\}")
MD = MarkdownIt("commonmark").enable("table")


def key(name):
    return name.replace("_", "-")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _text(s):
    """Escape text, then turn substitutions and questions into DITA elements."""
    out = html.escape(s, quote=False)
    out = SUB.sub(lambda m: f'<keyword keyref="{key(m.group(1))}"/>', out)
    return PLACEHOLDER.sub(lambda m: f'<draft-comment author="autonomous-author" disposition="open">NEEDS INPUT: {m.group(1).strip()}</draft-comment>', out)


def _inline(tok):
    out, link = [], None
    for c in tok.children or []:
        if c.type == "text":
            out.append(_text(c.content))
        elif c.type == "code_inline":
            out.append(f"<codeph>{html.escape(c.content, quote=False)}</codeph>")
        elif c.type in ("softbreak", "hardbreak"):
            out.append(" ")
        elif c.type == "link_open":
            href = c.attrs.get("href", "")
            link = re.sub(r"\.md(#|$)", r".dita\1", href)
            scope = ' scope="external" format="html"' if href.startswith("http") else ""
            out.append(f'<xref href="{html.escape(link)}"{scope}>')
        elif c.type == "link_close":
            out.append("</xref>")
        elif c.type in ("strong_open", "strong_close", "em_open", "em_close"):
            out.append({"strong_open": "<b>", "strong_close": "</b>", "em_open": "<i>", "em_close": "</i>"}[c.type])
    return "".join(out)


def topic(md_text, topic_id):
    toks = MD.parse(md_text)
    title, body, in_section, i = topic_id, [], False, 0
    row, cells = None, []
    while i < len(toks):
        t = toks[i]
        if t.type == "heading_open":
            text = _inline(toks[i + 1])
            if t.tag == "h1":
                title = text
            else:
                if in_section:
                    body.append("</section>")
                body.append(f'<section id="{slug(toks[i + 1].content)}"><title>{text}</title>')
                in_section = True
            i += 3
            continue
        if t.type == "paragraph_open":
            body.append(f"<p>{_inline(toks[i + 1])}</p>")
            i += 3
            continue
        if t.type == "fence":
            lang = t.info.strip().split()[0] if t.info.strip() else ""
            if lang.startswith("{"):  # a MyST directive such as toctree is not content
                i += 1
                continue
            oc = f' outputclass="language-{lang}"' if lang else ""
            body.append(f"<codeblock{oc}>{html.escape(t.content.rstrip(), quote=False)}</codeblock>")
        elif t.type == "table_open":
            body.append("<simpletable>")
        elif t.type == "table_close":
            body.append("</simpletable>")
        elif t.type == "tr_open":
            row, cells = ("sthead" if toks[i - 1].type == "thead_open" else "strow"), []
        elif t.type in ("th_open", "td_open"):
            cells.append(f"<stentry>{_inline(toks[i + 1])}</stentry>")
        elif t.type == "tr_close":
            body.append(f"<{row}>{''.join(cells)}</{row}>")
        elif t.type == "bullet_list_open":
            body.append("<ul>")
        elif t.type == "bullet_list_close":
            body.append("</ul>")
        elif t.type == "ordered_list_open":
            body.append("<ol>")
        elif t.type == "ordered_list_close":
            body.append("</ol>")
        elif t.type == "list_item_open":
            body.append("<li>")
        elif t.type == "list_item_close":
            body.append("</li>")
        i += 1
    if in_section:
        body.append("</section>")
    inner = "\n    ".join(b.replace("<li><p>", "<li>").replace("</p></li>", "</li>") for b in body)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n{TOPIC_DT}\n<topic id="{topic_id}">\n  <title>{title}</title>\n'
            f"  <body>\n    {inner}\n  </body>\n</topic>\n")


def ditamap(docs, subs):
    keys = "\n".join(f'  <keydef keys="{key(k)}"><topicmeta><keywords><keyword>{html.escape(str(v))}</keyword></keywords></topicmeta></keydef>'
                     for k, v in subs.items())
    index = (docs / "index.md").read_text()
    m = re.search(r"```\{toctree\}(.*?)```", index, re.S)
    entries = [l.strip() for l in (m.group(1) if m else "").splitlines() if l.strip() and not l.strip().startswith(":")]
    title = re.search(r"^#\s+(.+)$", index, re.M)
    refs = "\n".join(f'  <topicref href="{e}.dita"/>' for e in entries)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n{MAP_DT}\n<map>\n  <title>{html.escape(title.group(1) if title else "Docs")}</title>\n'
            f"{keys}\n{refs}\n</map>\n")


def convert(repo):
    """Return {dita path: text} for the MyST docs set in `repo`."""
    docs = pathlib.Path(repo) / "docs"
    subs = yaml.safe_load((docs / "substitutions.yml").read_text()) or {}
    out = {"dita/docs.ditamap": ditamap(docs, subs)}
    for p in sorted(docs.rglob("*.md")):
        if p.name == "index.md" or "_build" in p.parts:
            continue
        rel = p.relative_to(docs).with_suffix(".dita")
        out[f"dita/{rel}"] = topic(p.read_text(), p.stem)
    return out


def validate(files):
    """Validate each file against the DITA 1.3 DTDs through the OASIS catalog (xmllint, no network).

    Returns a list of errors. xmllint is used because the DITA DTDs nest entities more deeply
    than lxml allows; --huge lifts that limit for these trusted local DTDs only.
    """
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("xmllint"):
        return ["xmllint is not installed; DITA was not validated"]
    errors = []
    env = {**os.environ, "XML_CATALOG_FILES": str(VENDOR / "catalog.xml")}
    with tempfile.TemporaryDirectory() as d:
        for path, text in files.items():
            f = pathlib.Path(d) / pathlib.Path(path).name
            f.write_text(text)
            r = subprocess.run(["xmllint", "--huge", "--noout", "--valid", "--nonet", str(f)], capture_output=True, text=True, env=env)
            if r.returncode or r.stderr.strip():
                errors.append(f"{path}: " + " ".join(r.stderr.split())[:300])
    return errors


def diff(before, after):
    out = {}
    for path in sorted(set(before) | set(after)):
        a, b = before.get(path, ""), after.get(path, "")
        if a != b:
            out[path] = "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{path}", f"b/{path}", n=2))
    return out


def write(repo):
    """Regenerate dita/ from docs/ on disk. Returns (changed paths, validation errors)."""
    root = pathlib.Path(repo)
    files = convert(repo)
    changed = []
    for path, text in files.items():
        f = root / path
        if not f.exists() or f.read_text() != text:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
            changed.append(path)
    for f in (root / "dita").rglob("*"):
        rel = str(f.relative_to(root))
        if f.is_file() and rel not in files:
            f.unlink()
            changed.append(rel)
    return changed, validate(files)


def out_of_sync(repo):
    """Paths in dita/ that don't match what docs/ generates."""
    root = pathlib.Path(repo)
    return [p for p, t in convert(repo).items() if not (root / p).exists() or (root / p).read_text() != t]
