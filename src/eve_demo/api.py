import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from eve_demo.config import DATA_DIR, TOTAL_TIMEOUT
from eve_demo.models import Query
from eve_demo.store import pending_jobs, read, save, traces
from eve_demo.supervisor import build_graph, run_job


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string(str(DATA_DIR / "checkpoints.sqlite")) as saver:
        await saver.setup()
        app.state.graph = build_graph(saver)
        app.state.workers = set()

        def launch(task_id: str, resume: bool = False) -> None:
            work = asyncio.create_task(run_job(app.state.graph, task_id, resume))
            app.state.workers.add(work)
            work.add_done_callback(app.state.workers.discard)

        app.state.launch = launch
        for job in pending_jobs():
            launch(job["task_id"], True)
        yield
        workers = list(app.state.workers)
        for work in workers:
            work.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


app = FastAPI(title="EVE Multi-Agent Delegation Demo (independent)", lifespan=lifespan)


@app.get("/health")
async def health():
    import os

    return {"status": "ok", "service": "langgraph-supervisor", "pid": os.getpid()}


@app.post("/api/query", status_code=202)
async def query(request: Query):
    task_id = str(uuid4())
    save(
        "jobs",
        task_id,
        {
            "task_id": task_id,
            "thread_id": task_id,
            "status": "queued",
            "request": request.model_dump(),
            "result": None,
            "submitted_at": time.time(),
            "deadline_epoch": time.time() + TOTAL_TIMEOUT,
        },
    )
    app.state.launch(task_id)
    return {"task_id": task_id, "thread_id": task_id, "status": "queued"}


@app.get("/api/tasks/{task_id}")
async def task(task_id: str):
    job = read("jobs", task_id)
    if not job:
        raise HTTPException(404, "Unknown task")
    return job


@app.get("/api/tasks/{task_id}/trace")
async def task_trace(task_id: str):
    if not read("jobs", task_id):
        raise HTTPException(404, "Unknown task")
    return {"request_id": task_id, "events": traces(task_id)}


@app.get("/api/graph")
async def graph():
    return {"mermaid": app.state.graph.get_graph().draw_mermaid()}
