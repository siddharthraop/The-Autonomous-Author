"""HTTP API for the live demo: commit a feature, stream the agent's stages, review the draft."""
import collections
import difflib
import json
import os
import queue
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from author import __version__, demo

PER_IP, GLOBAL = int(os.environ.get("AUTHOR_RATE_IP", 10)), int(os.environ.get("AUTHOR_RATE_GLOBAL", 60))
HITS = collections.defaultdict(collections.deque)


def _limited(ip):
    now = time.time()
    for k in (ip, "*"):
        q = HITS[k]
        while q and now - q[0] > 3600:
            q.popleft()
    if len(HITS[ip]) >= PER_IP or len(HITS["*"]) >= GLOBAL:
        return True
    HITS[ip].append(now)
    HITS["*"].append(now)
    return False


def _code_preview(ops):
    src = (demo.SAMPLE / demo.SETTINGS).read_text()
    new = demo.apply_ops(src, ops)
    return "".join(difflib.unified_diff(src.splitlines(True), new.splitlines(True),
                                        f"a/{demo.SETTINGS}", f"b/{demo.SETTINGS}", n=2))


def create_app():
    app = FastAPI(title="The Autonomous Author", version=__version__)
    origins = os.environ.get("AUTHOR_CORS_ORIGINS", "https://siddharthraop.github.io,http://localhost:8000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health():
        live = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        return {"ok": True, "version": __version__, "model": os.environ.get("AUTHOR_MODEL", "gemini-3.8-flash") if live else "none"}

    @app.get("/api/samples")
    def samples():
        return [{k: s[k] for k in ("id", "title", "text", "why", "doc_type")} | {"diff": _code_preview(s["ops"])} for s in demo.SAMPLES]

    @app.post("/api/change-preview")
    async def change_preview(request: Request):
        body = await request.json()
        try:
            return {"diff": _code_preview(body.get("ops") or [])}
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/features")
    async def features(request: Request):
        spec = await request.json()
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        if _limited(ip):
            raise HTTPException(429, "This demo allows a few runs an hour per visitor. Try again later.")
        q = queue.Queue()

        def work():
            try:
                res = demo.run_feature(spec, lambda stage, detail="": q.put({"stage": stage, "detail": detail}))
                q.put({"stage": "done", "result": res})
            except ValueError as e:
                q.put({"stage": "error", "detail": str(e)})
            except Exception as e:  # report, never hang the stream
                q.put({"stage": "error", "detail": f"{type(e).__name__}: {e}"[:300]})
            q.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while (ev := q.get()) is not None:
                yield json.dumps(ev, default=str) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})

    def _get(fn, *a):
        try:
            return fn(*a)
        except KeyError:
            raise HTTPException(404, "This draft has expired. Drafts are kept for an hour; commit the feature again.")
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/runs/{rid}/answers")
    async def answers(rid: str, request: Request):
        body = await request.json()
        return _get(demo.answer, rid, body.get("answers") or {})

    @app.post("/api/runs/{rid}/approve")
    def approve(rid: str):
        return _get(demo.approve, rid)

    @app.get("/api/runs/{rid}/download")
    def download(rid: str):
        data = _get(demo.bundle, rid)
        return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="docs-draft-{rid}.zip"'})

    @app.get("/api/runs/{rid}/preview/{path:path}")
    def preview(rid: str, path: str):
        return FileResponse(_get(demo.preview, rid, path))

    return app


app = create_app()
