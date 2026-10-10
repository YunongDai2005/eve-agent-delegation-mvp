import asyncio
import json
import time
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import TaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, DataPart, Part, Task, TaskState
from a2a.utils import new_agent_text_message, new_task

from eve_demo.config import AGENT_URL, TOTAL_TIMEOUT
from eve_demo.models import Delegation
from eve_demo.retrieval import retrieve
from eve_demo.store import db, read, save, trace


class SQLiteTaskStore(TaskStore):
    async def save(self, task: Task, context: Any = None) -> None:
        await asyncio.to_thread(save, "remote_tasks", task.id, task.model_dump(mode="json"))

    async def get(self, task_id: str, context: Any = None) -> Task | None:
        data = await asyncio.to_thread(read, "remote_tasks", task_id)
        return Task.model_validate(data) if data else None

    async def delete(self, task_id: str, context: Any = None) -> None:
        def remove() -> None:
            with db() as conn:
                conn.execute("DELETE FROM remote_tasks WHERE id=?", (task_id,))

        await asyncio.to_thread(remove)


class RetrievalExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.active: dict[str, asyncio.Task] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A execution requires a message")
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work(new_agent_text_message("Retrieving evidence via MCP"))
        request_id = task.id
        try:
            raw = context.get_user_input()
            payload = Delegation.model_validate_json(raw)
            if not payload.plan.accepted:
                raise ValueError("Retrieval requires an accepted nonempty tool plan")
            request_id = payload.request_id
            trace(
                request_id, "a2a.agent", "working", a2a_task_id=task.id, mode=payload.request.mode
            )
            lock = self.locks.setdefault(request_id, asyncio.Lock())
            async with lock:
                cached = read("receipts", request_id)
                if cached:
                    result = cached
                    trace(request_id, "a2a.receipt", "replayed", a2a_task_id=task.id)
                else:
                    work = asyncio.create_task(retrieve(payload))
                    self.active[task.id] = work
                    remaining = (
                        payload.deadline_epoch - time.time()
                        if payload.deadline_epoch is not None
                        else TOTAL_TIMEOUT - 5
                    )
                    result = await asyncio.wait_for(work, max(0, min(remaining, TOTAL_TIMEOUT - 5)))
                    save("receipts", request_id, result)
            await updater.add_artifact(
                [Part(root=DataPart(data=result))], name="eo-evidence", last_chunk=True
            )
            if result["status"] == "failed":
                await updater.failed(new_agent_text_message("All requested data queries failed"))
            else:
                await updater.complete()
            trace(request_id, "a2a.agent", result["status"], a2a_task_id=task.id)
        except asyncio.CancelledError:
            await updater.cancel()
            trace(request_id, "a2a.agent", "canceled", a2a_task_id=task.id)
        except Exception as exc:
            # Provider errors can contain credentials: expose only type here.
            trace(request_id, "a2a.agent", "failed", error=type(exc).__name__)
            await updater.failed(new_agent_text_message(type(exc).__name__))
        finally:
            self.active.pop(task.id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            work = self.active.get(context.current_task.id)
            if work:
                work.cancel()
            else:
                updater = TaskUpdater(
                    event_queue, context.current_task.id, context.current_task.context_id
                )
                await updater.update_status(TaskState.canceled, final=True)


card = AgentCard(
    name="EO Retrieval Agent (independent EVE demo)",
    description=(
        "Retrieves GDACS hazards and candidate EO Dashboard collections via official MCP tools."
    ),
    url=AGENT_URL + "/",
    version="0.1.0",
    protocol_version="0.3.0",
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    capabilities=AgentCapabilities(streaming=False, push_notifications=False),
    skills=[
        AgentSkill(
            id="eo-retrieval",
            name="Disaster and EO resource retrieval",
            description=(
                "Accepts a JSON delegation plan; returns source-linked evidence artifacts."
            ),
            tags=["earth-observation", "gdacs", "mcp"],
            examples=[
                json.dumps(
                    {
                        "request_id": "00000000-0000-0000-0000-000000000001",
                        "request": {"query": "Find a recent flood", "mode": "live"},
                        "plan": {
                            "rationale": "Search flood hazards",
                            "calls": [
                                {
                                    "server": "gdacs",
                                    "tool": "search_gdacs_events",
                                    "arguments": {"eventlist": "FL"},
                                }
                            ],
                        },
                    }
                )
            ],
        )
    ],
)
handler = DefaultRequestHandler(agent_executor=RetrievalExecutor(), task_store=SQLiteTaskStore())
app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
