import json
import time
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import DataPart, Message, Part, Role, Task, TaskQueryParams, TextPart

from eve_demo.config import AGENT_URL, TOTAL_TIMEOUT
from eve_demo.models import Delegation
from eve_demo.store import trace


async def delegate(payload: Delegation) -> dict:
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=TOTAL_TIMEOUT - 10, trust_env=False) as http:
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        trace(payload.request_id, "a2a.discover", "success", agent=card.name, url=card.url)
        client = ClientFactory(
            ClientConfig(
                httpx_client=http, streaming=False, accepted_output_modes=["application/json"]
            )
        ).create(card)
        message = Message(
            message_id=str(uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=payload.model_dump_json()))],
            context_id=payload.request_id,
        )
        trace(
            payload.request_id,
            "a2a.delegate",
            "started",
            agent_url=AGENT_URL,
            tools=[call.tool for call in payload.plan.calls],
        )
        remote: Task | None = None
        async for event in client.send_message(message):
            if isinstance(event, tuple):
                remote = event[0]
        if remote is None:
            raise RuntimeError("A2A agent did not return a Task")
        # Exercise the independent tasks/get protocol path as well as message/send.
        fetched = await client.get_task(TaskQueryParams(id=remote.id))
        trace(
            payload.request_id,
            "a2a.get_task",
            fetched.status.state.value,
            a2a_task_id=fetched.id,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        for artifact in fetched.artifacts or []:
            for part in artifact.parts:
                if isinstance(part.root, DataPart):
                    result = dict(part.root.data)
                    result["a2a_task_id"] = fetched.id
                    result["a2a_state"] = fetched.status.state.value
                    return result
        raise RuntimeError(
            "A2A task returned no structured evidence artifact: " + fetched.status.state.value
        )


async def inspect_card() -> dict:
    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        return json.loads(card.model_dump_json(by_alias=True, exclude_none=True))
