from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

_tasks: dict[str, dict[str, Any]] = {}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html")


@router.post("/api/collect")
async def start_collect(request: Request):
    body = await request.json()
    topic = str(body.get("topic", "")).strip()
    if not topic:
        topic = request.app.state.settings.workflow.default_topic

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "id": task_id,
        "topic": topic,
        "status": "running",
        "progress": [],
        "result": None,
        "started_at": time.time(),
    }

    asyncio.create_task(_run_collection(request.app, task_id, topic))
    return JSONResponse({"task_id": task_id, "topic": topic})


@router.get("/api/status/{task_id}")
async def task_status_sse(request: Request, task_id: str):
    if task_id not in _tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    async def event_generator():
        last_index = 0
        while True:
            if await request.is_disconnected():
                break

            task = _tasks.get(task_id)
            if not task:
                break

            progress = task["progress"]
            while last_index < len(progress):
                yield {
                    "event": "progress",
                    "data": json.dumps(progress[last_index], ensure_ascii=False),
                }
                last_index += 1

            if task["status"] in ("completed", "failed"):
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "status": task["status"],
                        "result": task.get("result"),
                        "error": task.get("error"),
                    }, ensure_ascii=False),
                }
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.get("/api/reports")
async def list_reports(request: Request):
    output_dir = request.app.state.root_dir / request.app.state.settings.output.directory
    if not output_dir.exists():
        return JSONResponse({"reports": []})

    reports = []
    for f in sorted(output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        reports.append({
            "name": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })
    return JSONResponse({"reports": reports})


@router.get("/api/reports/{filename}")
async def get_report(request: Request, filename: str):
    output_dir = request.app.state.root_dir / request.app.state.settings.output.directory
    file_path = output_dir / filename
    if not file_path.exists() or not file_path.suffix == ".md":
        return JSONResponse({"error": "Report not found"}, status_code=404)

    content = file_path.read_text(encoding="utf-8")
    return JSONResponse({"filename": filename, "content": content})


async def _run_collection(app, task_id: str, topic: str):
    task = _tasks[task_id]
    logger = app.state.logger

    class ProgressHandler(object):
        def __init__(self):
            import logging
            self.handler = logging.Handler()
            self.handler.emit = self._emit

        def _emit(self, record):
            task["progress"].append({
                "time": time.time(),
                "level": record.levelname,
                "message": record.getMessage(),
            })

    progress = ProgressHandler()
    logger.addHandler(progress.handler)

    try:
        if app.state.collector is None:
            from news_collector.collector import EnvNewsCollector
            app.state.collector = EnvNewsCollector(
                settings=app.state.settings,
                root_dir=app.state.root_dir,
                logger=logger,
            )

        task["progress"].append({
            "time": time.time(),
            "level": "INFO",
            "message": f"开始采集环境新闻: {topic}",
        })

        result = await asyncio.to_thread(app.state.collector.collect, topic)
        task["status"] = "completed"
        task["result"] = {
            "report_title": result.get("report_title", ""),
            "output_path": result.get("output_path", ""),
            "markdown": result.get("markdown", ""),
        }
        task["progress"].append({
            "time": time.time(),
            "level": "INFO",
            "message": "采集完成!",
        })
    except Exception as exc:
        logger.exception("Collection failed: %s", exc)
        task["status"] = "failed"
        task["error"] = str(exc)
        task["progress"].append({
            "time": time.time(),
            "level": "ERROR",
            "message": f"采集失败: {exc}",
        })
    finally:
        logger.removeHandler(progress.handler)
