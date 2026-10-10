import asyncio
import json
import time
from uuid import uuid4

import httpx
import pytest
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, TaskQueryParams, TextPart
from conftest import load_cases
from pydantic import ValidationError

from demo import run_query
from eve_demo.models import Query, ToolCall
from eve_demo.retrieval import interpret
from eve_demo.store import redact


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_full_mock_protocol_chain(services, case):
    packet = run_query(
        services,
        {"query": case["query"], "mode": "mock", "fault": case.get("fault", "none")},
        verbose=False,
    )
    final = packet["job"]["result"]
    assert final["status"] == case["expected"]
    assert final["mode"] == "mock"
    assert sorted(c["tool"] for c in final["plan"]["calls"]) == sorted(case["tools"])
    if case["tools"]:
        events = packet["trace"]
        assert any(e["node"] == "a2a.get_task" for e in events)
        agent_pids = {e["pid"] for e in events if e["node"] == "a2a.agent"}
        supervisor_pids = {e["pid"] for e in events if e["node"] == "plan"}
        assert agent_pids and agent_pids.isdisjoint(supervisor_pids)
        assert any(e["node"] == "mcp.call" for e in events)
        assert all(not r["event_match_verified"] for r in final["candidate_eo_resources"])
    if case["id"] == "country":
        assert final["retrieved_events"][0]["properties"]["country"] == "Bangladesh"
    if case["id"] == "red-flood":
        assert final["retrieved_events"][0]["properties"]["alertlevel"] == "Red"
    if case["id"] == "transient-recovery":
        assert any(e["node"] == "mcp.retry" for e in packet["trace"])
        assert final["tool_results"][0]["attempts"] == 2


def test_api_validation_and_unknown_task(services):
    with httpx.Client(base_url=services.api_url, trust_env=False) as client:
        assert client.post("/api/query", json={"query": "   "}).status_code == 422
        assert (
            client.post("/api/query", json={"query": "flood", "fault": "permanent"}).status_code
            == 422
        )
        assert client.get("/api/tasks/missing").status_code == 404
        assert client.get("/api/tasks/missing/trace").status_code == 404
        assert "delegate" in client.get("/api/graph").json()["mermaid"]


def test_secret_redaction():
    secret = redact(
        {
            "api_key": "example",
            "arguments": {"country": "token=abcdef"},
            "error": "Bearer abcdef sk-test1234 password=12345",
        }
    )
    text = json.dumps(secret)
    assert not any(s in text for s in ("example", "abcdef", "test1234", "12345"))


def test_tool_schema_rejects_invented_tool_arguments():
    with pytest.raises(ValidationError):
        ToolCall(server="gdacs", tool="search_gdacs_events", arguments={"eventlist": "XX"})
    with pytest.raises(ValidationError):
        ToolCall(server="eodashboard", tool="search_gdacs_events")
    with pytest.raises(ValidationError):
        Query(query="flood", mode="live", fault="timeout")


def test_gdacs_filters_hazard_and_sorts_latest():
    call = ToolCall(server="gdacs", tool="search_gdacs_events", arguments={"eventlist": "FL"})
    text = json.dumps(
        {
            "features": [
                {"properties": {"eventtype": hazard, "todate": date}}
                for hazard, date in (("FL", "2020"), ("EQ", "2026"), ("FL", "2025"))
            ]
        }
    )
    status, records = interpret(call, text)
    assert status == "success"
    assert [r["properties"]["todate"] for r in records] == ["2025", "2020"]


def test_independent_a2a_client_rejects_bad_payload(services):
    async def invoke():
        async with httpx.AsyncClient(timeout=15, trust_env=False) as http:
            card = await A2ACardResolver(http, services.agent_url).get_agent_card()
            client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)
            message = Message(
                message_id=str(uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text="not a valid JSON delegation"))],
            )
            remote = None
            async for event in client.send_message(message):
                if isinstance(event, tuple):
                    remote = event[0]
            assert remote is not None
            fetched = await client.get_task(TaskQueryParams(id=remote.id))
            assert fetched.status.state.value == "failed"
            assert not fetched.artifacts

    asyncio.run(invoke())


def test_sqlite_crash_resume_without_replanning(services):
    with httpx.Client(base_url=services.api_url, timeout=5, trust_env=False) as client:
        task_id = client.post(
            "/api/query", json={"query": "Find flood resources", "mode": "mock"}
        ).json()["task_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            events = client.get(f"/api/tasks/{task_id}/trace").json()["events"]
            if any(e["node"] == "a2a.delegate" for e in events):
                break
            time.sleep(0.05)
        else:
            pytest.fail("Delegation did not start")
    services.restart_supervisor()
    with httpx.Client(base_url=services.api_url, timeout=5, trust_env=False) as client:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            job = client.get(f"/api/tasks/{task_id}").json()
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        assert job["status"] == "success"
        events = client.get(f"/api/tasks/{task_id}/trace").json()["events"]
        assert any(e["node"] == "checkpoint.resume" for e in events)
        assert sum(e["node"] == "plan" and e["status"] == "success" for e in events) == 1
        from eve_demo.config import ROOT

        (ROOT / "evidence" / "checkpoint-recovery.json").write_text(
            json.dumps({"job": job, "trace": events}, indent=2), encoding="utf-8"
        )
