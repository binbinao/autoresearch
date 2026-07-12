"""AutoResearch beginner console — FastAPI entrypoint.

Usage:
  uv sync --extra ui
  uv run --extra ui python -m web.app
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.loop_engine import PROGRAM_MD, REPO_ROOT, engine

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="AutoResearch Console", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class BranchBody(BaseModel):
    tag: str = Field(..., min_length=1, max_length=64)


class EnvBody(BaseModel):
    overrides: dict[str, str] = Field(default_factory=dict)


class PresetBody(BaseModel):
    name: str


class RunBody(BaseModel):
    description: str = "experiment"


class DecideBody(BaseModel):
    action: str


class ProgramBody(BaseModel):
    content: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    return engine.status()


@app.post("/api/branch")
def api_branch(body: BranchBody) -> dict[str, Any]:
    try:
        branch = engine.create_branch(body.tag)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "branch": branch}


@app.post("/api/env")
def api_env(body: EnvBody) -> dict[str, Any]:
    engine.set_env_overrides(body.overrides)
    return {"ok": True, "overrides": engine.snap.env_overrides}


@app.post("/api/preset")
def api_preset(body: PresetBody) -> dict[str, Any]:
    try:
        preset = engine.apply_preset(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "overrides": preset}


@app.post("/api/prepare")
def api_prepare() -> dict[str, Any]:
    try:
        engine.start_prepare()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/run")
def api_run(body: RunBody) -> dict[str, Any]:
    try:
        engine.start_run(body.description)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/demo")
def api_demo(body: RunBody) -> dict[str, Any]:
    try:
        engine.start_demo(body.description)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/stop")
def api_stop() -> dict[str, Any]:
    engine.stop()
    return {"ok": True}


@app.post("/api/decide")
def api_decide(body: DecideBody) -> dict[str, Any]:
    try:
        return engine.decide(body.action)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/program")
def api_get_program() -> dict[str, str]:
    if not PROGRAM_MD.exists():
        return {"content": ""}
    return {"content": PROGRAM_MD.read_text(encoding="utf-8")}


@app.put("/api/program")
def api_put_program(body: ProgramBody) -> dict[str, Any]:
    PROGRAM_MD.write_text(body.content, encoding="utf-8")
    engine.checkpoint("已保存 program.md")
    return {"ok": True}


@app.get("/api/results")
def api_results() -> dict[str, Any]:
    engine.refresh_static()
    return {"rows": engine.snap.history, "best_val_bpb": engine.snap.best_val_bpb}


@app.get("/api/log/stream")
def api_log_stream(from_index: int = 0) -> StreamingResponse:
    def gen():
        yield f"data: {json.dumps({'type': 'hello', 'from': from_index})}\n\n"
        for line in engine.iter_log(from_index):
            yield f"data: {json.dumps({'type': 'line', 'text': line})}\n\n"
        status = engine.status()
        yield f"data: {json.dumps({'type': 'done', 'state': status['state']})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:
    import uvicorn

    print(f"AutoResearch Console → http://127.0.0.1:8765  (repo: {REPO_ROOT})")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
