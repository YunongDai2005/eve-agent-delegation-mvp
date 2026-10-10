import asyncio
import json
import re
import sys
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from eve_demo.config import ROOT, TOOL_TIMEOUT
from eve_demo.models import Delegation, ToolCall
from eve_demo.store import trace

SOURCES = {
    "gdacs": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
    "eodashboard": "https://esa-eodashboards.github.io/eodashboard-catalog/trilateral/catalog.json",
}


class DataUnavailable(Exception):
    pass


def interpret(call: ToolCall, text: str) -> tuple[str, list[dict[str, Any]]]:
    """Decode upstream output, not LLM-generated facts. Preserve raw output separately."""
    if call.server == "gdacs":
        data = json.loads(text)
        if "error" in data:
            if "No results" in data["error"]:
                return "no_data", []
            raise DataUnavailable(data["error"])
        if not isinstance(data.get("features"), list):
            raise ValueError("GDACS response has no GeoJSON features list")
        features = data["features"]
        hazard = call.arguments.get("eventlist")
        if hazard:
            features = [f for f in features if f.get("properties", {}).get("eventtype") == hazard]
        features = sorted(
            features, key=lambda f: str(f.get("properties", {}).get("todate", "")), reverse=True
        )[:5]
        records = []
        for item in features:
            props = item.get("properties", {})
            source = props.get("url") or props.get("reporturl") or SOURCES["gdacs"]
            if isinstance(source, dict):
                source = source.get("report") or SOURCES["gdacs"]
            records.append(
                {
                    "kind": "retrieved_event",
                    "properties": props,
                    "geometry": item.get("geometry"),
                    "source_url": source,
                    "date_claim": "Dates are the upstream event dates; recency is not guaranteed",
                }
            )
            end_date = props.get("todate") or props.get("fromdate")
            try:
                reported = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
                if reported.tzinfo is None:
                    reported = reported.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - reported).total_seconds() / 86400
                records[-1]["age_days_from_reported_end"] = round(age, 1)
                records[-1]["within_30_days"] = 0 <= age <= 30
            except ValueError:
                records[-1]["within_30_days"] = None
        return ("success" if records else "no_data"), records
    if text.startswith("No collections") or "No results found" in text:
        return "no_data", []
    if text.startswith("{"):
        data = json.loads(text)
        if "error" in data:
            raise DataUnavailable(data["error"])
    if not text.startswith("Found "):
        raise ValueError("Unrecognized EO Dashboard collection response")
    urls = re.findall(r"URL:\s*(https?://\S+)", text)
    if not urls:
        raise ValueError("Collection response contains no source URLs")
    return "success", [
        {
            "kind": "candidate_eo_resource",
            "source_url": url,
            "event_match_verified": False,
        }
        for url in urls
    ]


async def retrieve(payload: Delegation) -> dict:
    request_id = payload.request_id
    request = payload.request
    start = time.perf_counter()
    outcomes: list[dict] = []
    async with AsyncExitStack() as stack:
        sessions: dict[str, ClientSession] = {}
        for call in payload.plan.calls:
            if call.server not in sessions:
                if request.mode == "mock":
                    arguments = ["-m", "eve_demo.mock_mcp", "--fault", request.fault]
                else:
                    arguments = [
                        str(ROOT / "vendor" / "eve" / call.server / "server.py"),
                        "--transport",
                        "stdio",
                    ]
                params = StdioServerParameters(command=sys.executable, args=arguments)
                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                tools = await session.list_tools()
                trace(
                    request_id,
                    "mcp.discover",
                    "success",
                    server=call.server,
                    tools=[tool.name for tool in tools.tools],
                    mode=request.mode,
                )
                sessions[call.server] = session
            session = sessions[call.server]
            timeout = 0.3 if request.mode == "mock" and request.fault == "timeout" else TOOL_TIMEOUT
            for attempt in range(1, 3):
                call_start = time.perf_counter()
                trace(
                    request_id,
                    "mcp.call",
                    "started",
                    server=call.server,
                    tool=call.tool,
                    arguments=call.arguments,
                    attempt=attempt,
                    mode=request.mode,
                )
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(call.tool, call.arguments), timeout
                    )
                    output = "\n".join(c.text for c in result.content if c.type == "text")
                    if result.isError:
                        raise DataUnavailable(output)
                    status, records = interpret(call, output)
                    if call.server == "gdacs" and "recent" in request.query.lower():
                        records = [r for r in records if r.get("within_30_days") is True]
                        status = "success" if records else "no_data"
                    outcome = {
                        "server": call.server,
                        "tool": call.tool,
                        "arguments": call.arguments,
                        "status": status,
                        "records": records,
                        "raw_output": output,
                        "source_url": SOURCES[call.server]
                        if request.mode == "live"
                        else "https://example.invalid/mock-source",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "attempts": attempt,
                        "date_policy": "recent: end date within 30 days; naive dates assumed UTC",
                    }
                    outcomes.append(outcome)
                    trace(
                        request_id,
                        "mcp.call",
                        status,
                        server=call.server,
                        tool=call.tool,
                        attempt=attempt,
                        duration_ms=round((time.perf_counter() - call_start) * 1000, 2),
                        sources=[r["source_url"] for r in records],
                        mode=request.mode,
                    )
                    break
                except (DataUnavailable, ValueError, TimeoutError) as exc:
                    error = "Tool timeout" if isinstance(exc, TimeoutError) else str(exc)[:500]
                    trace(
                        request_id,
                        "mcp.call",
                        "error",
                        tool=call.tool,
                        attempt=attempt,
                        duration_ms=round((time.perf_counter() - call_start) * 1000, 2),
                        error=error,
                    )
                    retry = attempt == 1 and not isinstance(exc, ValueError)
                    if retry:
                        trace(request_id, "mcp.retry", "recovering", tool=call.tool, attempt=2)
                        await asyncio.sleep(0.15)
                    else:
                        outcomes.append(
                            {
                                "server": call.server,
                                "tool": call.tool,
                                "status": "failed",
                                "records": [],
                                "error": error,
                                "attempts": attempt,
                            }
                        )
                        break
    statuses = [o["status"] for o in outcomes]
    status = (
        "success"
        if all(s == "success" for s in statuses)
        else (
            "partial"
            if "success" in statuses
            else ("failed" if "failed" in statuses else "no_data")
        )
    )
    return {
        "request_id": request_id,
        "mode": request.mode,
        "status": status,
        "outcomes": outcomes,
        "retrieval_ms": round((time.perf_counter() - start) * 1000, 2),
    }
