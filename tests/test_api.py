"""The demo API: a sample feature streams its stages and ends in a reviewable draft."""
import json

from fastapi.testclient import TestClient

from api.main import create_app


def test_sample_feature_end_to_end(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    c = TestClient(create_app())
    samples = c.get("/api/samples").json()
    assert {s["id"] for s in samples} >= {"default", "field", "minimum", "rollout"}
    assert "+        \"default\": 30," in samples[0]["diff"] or '"default": 30' in samples[0]["diff"]
    lines = [json.loads(l) for l in c.post("/api/features", json={"sample": "default"}).text.splitlines()]
    stages = [l["stage"] for l in lines]
    assert stages[0] == "commit" and stages[-1] == "done"
    r = lines[-1]["result"]
    assert r["score"]["total"] == 10.0 and all(e["ok"] for e in r["expected"]) and not r["dita_errors"]
    assert "dita/docs.ditamap" in r["dita_diff"] and "docs/substitutions.yml" in r["myst_diff"]
    assert c.post(f"/api/runs/{r['run_id']}/approve").json()["status"] == "approved"
    assert c.get(f"/api/runs/{r['run_id']}/download").headers["content-type"] == "application/zip"
    assert c.get(f"/api/runs/{r['run_id']}/preview/{r['preview'][0]}").status_code == 200
    assert c.get(f"/api/runs/{r['run_id']}/preview/../../etc/passwd").status_code == 404


def test_custom_feature_is_validated():
    c = TestClient(create_app())
    assert c.post("/api/change-preview", json={"ops": [{"op": "set", "setting": "udp", "attr": "default", "value": 0}]}).status_code == 400
    bad = [json.loads(l) for l in c.post("/api/features", json={"title": "x", "text": "y", "ops": [{"op": "field", "name": "os.system"}]}).text.splitlines()]
    assert bad[-1]["stage"] == "error"
