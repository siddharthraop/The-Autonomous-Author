"""Minimal GitHub REST client. Uses the workflow's GITHUB_TOKEN; never stores it."""
import json
import os
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHub:
    def __init__(self, repo=None, token=None):
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    @property
    def enabled(self):
        return bool(self.repo and self.token)

    def call(self, method, path, body=None):
        req = urllib.request.Request(f"{API}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            return json.loads(data) if data else {}

    def r(self, method, sub, body=None):
        return self.call(method, f"/repos/{self.repo}{sub}", body)

    def pulls_for_commit(self, sha):
        try:
            return self.r("GET", f"/commits/{sha}/pulls")
        except Exception:
            return []

    def issue(self, n):
        return self.r("GET", f"/issues/{n}")

    def comment(self, n, body):
        return self.r("POST", f"/issues/{n}/comments", {"body": body})

    def commit_comment(self, sha, body):
        return self.r("POST", f"/commits/{sha}/comments", {"body": body})

    def labels(self, n, labels):
        return self.r("POST", f"/issues/{n}/labels", {"labels": labels})

    def open_pr(self, head, base, title, body, draft=True):
        return self.r("POST", "/pulls", {"head": head, "base": base, "title": title, "body": body, "draft": draft})

    def status(self, sha, state, context, description, url=None):
        body = {"state": state, "context": context, "description": description[:140]}
        if url:
            body["target_url"] = url
        return self.r("POST", f"/statuses/{sha}", body)

    def open_issue(self, title, body, labels):
        return self.r("POST", "/issues", {"title": title, "body": body, "labels": labels})

    def search_open_issues(self, label):
        return self.r("GET", f"/issues?state=open&labels={label}")
