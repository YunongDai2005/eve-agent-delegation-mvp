"""Export the actual compiled LangGraph, discovered MCP schemas and actual A2A Task."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import TaskQueryParams
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import run_query  # noqa: E402
from eve_demo.config import ROOT  # noqa: E402
from eve_demo.processes import Services  # noqa: E402


async def capture_tools() -> list[dict]:
    output = []
    for name in ("gdacs", "eodashboard"):
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                str(ROOT / "vendor" / "eve" / name / "server.py"),
                "--transport",
                "stdio",
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                output.append({"server": name, "tools": [t.model_dump() for t in tools.tools]})
    return output


async def capture_task(url: str, task_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
        card = await A2ACardResolver(http, url).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)
        task = await client.get_task(TaskQueryParams(id=task_id))
        return task.model_dump(mode="json", by_alias=True, exclude_none=True)


def main() -> None:
    with Services(9140, 9141) as services:
        live_packet = ROOT / "evidence" / "last-live.json"
        packet = (
            json.loads(live_packet.read_text(encoding="utf-8")) if live_packet.exists()
            else run_query(services, {"query": "Find flood events", "mode": "mock"}, verbose=False)
        )
        with httpx.Client(trust_env=False) as client:
            card = client.get(services.agent_url + "/.well-known/agent-card.json").json()
            graph = client.get(services.api_url + "/api/graph").json()["mermaid"]
        task = asyncio.run(capture_task(services.agent_url, packet["job"]["result"]["a2a_task_id"]))
    tools = asyncio.run(capture_tools())
    (ROOT / "docs" / "langgraph.mmd").write_text(graph, encoding="utf-8")
    for name, data in (("agent-card", card), ("mcp-tools", tools), ("a2a-task", task)):
        (ROOT / "evidence" / f"{name}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    print("Exported actual graph, SDK task/card and official MCP list_tools schemas.")


if __name__ == "__main__":
    main()
