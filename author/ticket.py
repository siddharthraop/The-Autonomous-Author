"""Doc ticket reader. Jira Cloud REST API v3 when configured, a GitHub issue otherwise.

A doc ticket carries what the doc kickoff decided: doc type, audience and pages
in scope. Fields are read from lines such as "Doc type: task".
"""
import base64
import json
import os
import re
import urllib.request

FIELDS = {"doc_type": r"Doc type", "audience": r"Audience", "pages": r"Pages"}


def parse_fields(text):
    out = {}
    for key, label in FIELDS.items():
        m = re.search(rf"^\s*[*_]*{label}[*_]*\s*:\s*(.+)$", text or "", re.I | re.M)
        if m:
            out[key] = m.group(1).strip()
    if "pages" in out:
        out["pages"] = [p.strip(" `") for p in re.split(r"[,\s]+", out["pages"]) if p.strip(" `")]
    return out


def _jira(key):
    base, email, token = (os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"))
    if not (base and email and token):
        return None
    req = urllib.request.Request(f"{base.rstrip('/')}/rest/api/3/issue/{key}?fields=summary,description")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode())
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    desc = json.dumps(data["fields"].get("description"))  # Atlassian document format, searched as text
    text = re.sub(r'\\n|"type":\s*"\w+"|[{}\[\],"]', " ", desc)
    return {"ref": key, "system": "jira", "title": data["fields"]["summary"], "text": text,
            "url": f"{base.rstrip('/')}/browse/{key}"}


def read_ticket(ref, gh=None, local=None):
    """Return the ticket as a dict, or None. `local` is a JSON file used in tests and replays."""
    t = None
    if local:
        with open(local) as f:
            t = json.load(f)
    elif ref and ref.startswith("#") and gh and gh.enabled:
        i = gh.issue(int(ref[1:]))
        t = {"ref": ref, "system": "github", "number": i["number"], "title": i["title"],
             "text": i.get("body") or "", "url": i["html_url"]}
    elif ref and not ref.startswith("#"):
        t = _jira(ref)
    if t:
        t.update(parse_fields(t.get("text", "")))
    return t
