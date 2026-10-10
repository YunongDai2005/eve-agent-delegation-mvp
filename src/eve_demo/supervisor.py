import asyncio
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from eve_demo.a2a_client import delegate
from eve_demo.config import TOTAL_TIMEOUT
from eve_demo.models import Delegation, Plan, Query
from eve_demo.planner import plan_request
from eve_demo.store import read, save, trace


class State(TypedDict, total=False):
    request_id: str
    request: dict
    plan: dict
    retrieval: dict
    attempt: int
    error: str
    final: dict
    deadline_epoch: float


async def plan_node(state: State) -> dict:
    start = time.perf_counter()
    trace(state["request_id"], "plan", "started")
    try:
        plan = await plan_request(Query.model_validate(state["request"]))
        trace(
            state["request_id"],
            "plan",
            "success",
            planner=plan.planner,
            accepted=plan.accepted,
            tools=[c.tool for c in plan.calls],
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return {"plan": plan.model_dump(), "attempt": 0, "error": ""}
    except Exception as exc:
        trace(state["request_id"], "plan", "failed", error=type(exc).__name__)
        return {
            "plan": {
                "accepted": False,
                "calls": [],
                "rationale": "Planning failed",
                "planner": state["request"]["planner"],
            },
            "error": type(exc).__name__,
        }


async def delegate_node(state: State) -> dict:
    attempt = state.get("attempt", 0) + 1
    try:
        result = await delegate(
            Delegation(
                request_id=state["request_id"],
                request=Query.model_validate(state["request"]),
                plan=Plan.model_validate(state["plan"]),
                deadline_epoch=state.get("deadline_epoch"),
            )
        )
        return {"retrieval": result, "attempt": attempt, "error": ""}
    except Exception as exc:
        trace(state["request_id"], "delegate", "failed", attempt=attempt, error=type(exc).__name__)
        return {"error": type(exc).__name__, "attempt": attempt}


async def recover_node(state: State) -> dict:
    trace(
        state["request_id"],
        "recover",
        "retrying" if state["attempt"] < 2 else "exhausted",
        attempt=state["attempt"],
        error=state["error"],
    )
    if state["attempt"] < 2:
        await asyncio.sleep(0.25)
    return {}


async def synthesize_node(state: State) -> dict:
    retrieval = state.get("retrieval", {})
    events: list[dict] = []
    candidates: list[dict] = []
    sources: list[str] = []
    warnings: list[str] = []
    for outcome in retrieval.get("outcomes", []):
        for record in outcome.get("records", []):
            if record["kind"] == "retrieved_event":
                events.append(record)
            else:
                candidates.append(record)
            sources.append(record["source_url"])
        if outcome["status"] != "success":
            warnings.append(f"{outcome['tool']}: {outcome['status']} " + outcome.get("error", ""))
    status = retrieval.get("status", "failed" if state.get("error") else "rejected")
    final = {
        "request_id": state["request_id"],
        "mode": state["request"]["mode"],
        "planner": state["plan"]["planner"],
        "status": status,
        "plan": state["plan"],
        "a2a_task_id": retrieval.get("a2a_task_id"),
        "a2a_state": retrieval.get("a2a_state"),
        "retrieved_events": events,
        "candidate_eo_resources": candidates,
        "sources": list(dict.fromkeys(sources)),
        "analysis_suggestions": [
            {
                "kind": "general_guidance_not_retrieved_evidence",
                "text": "For flood monitoring, compare pre/post-event radar acquisitions to assess "
                "inundation; validate acquisition dates, AOI coverage, terrain and processing "
                "before interpreting change. Optical data can complement radar when cloud permits.",
            }
        ]
        if events or candidates
        else [],
        "limitations": [
            "Catalogue candidates are not verified satellite imagery for any GDACS event.",
            "Recent means reported end within 30 days; naive GDACS timestamps are assumed UTC.",
            "Rules planner is limited; enable planner=llm for real model decisions.",
        ],
        "warnings": warnings,
        "error": state.get("error") or None,
        "tool_results": retrieval.get("outcomes", []),
    }
    trace(state["request_id"], "synthesize", status, sources=final["sources"])
    return {"final": final}


def build_graph(checkpointer: Any = None) -> Any:
    graph = StateGraph(State)
    graph.add_node("plan", plan_node)
    graph.add_node("delegate", delegate_node)
    graph.add_node("recover", recover_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan",
        lambda s: "delegate" if s["plan"]["accepted"] else "synthesize",
        {"delegate": "delegate", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "delegate",
        lambda s: "recover" if s.get("error") else "synthesize",
        {"recover": "recover", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "recover",
        lambda s: "delegate" if s["attempt"] < 2 else "synthesize",
        {"delegate": "delegate", "synthesize": "synthesize"},
    )
    graph.add_edge("synthesize", END)
    return graph.compile(checkpointer=checkpointer)


async def run_job(graph: Any, request_id: str, resume: bool = False) -> None:
    job = read("jobs", request_id)
    if job is None:
        return
    start = time.perf_counter()
    job["status"] = "running"
    save("jobs", request_id, job)
    deadline = job.get("deadline_epoch", time.time() + TOTAL_TIMEOUT)
    config = {"configurable": {"thread_id": request_id}, "recursion_limit": 14}
    try:
        snapshot = await graph.aget_state(config)
        if resume:
            trace(request_id, "checkpoint.resume", "restored", next_nodes=list(snapshot.next))
        if snapshot.values and not snapshot.next:
            result = snapshot.values
        else:
            initial = (
                None
                if snapshot.values
                else {
                    "request_id": request_id,
                    "request": job["request"],
                    "deadline_epoch": deadline,
                }
            )
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("Persisted task deadline expired")
            result = await asyncio.wait_for(graph.ainvoke(initial, config), remaining)
        final = result["final"]
        final["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        final["total_elapsed_ms"] = round(
            (time.time() - job.get("submitted_at", time.time())) * 1000, 2
        )
        job.update(status=final["status"], result=final)
        trace(request_id, "task", job["status"], duration_ms=final["latency_ms"])
    except asyncio.CancelledError:
        trace(request_id, "checkpoint", "interrupted")
        # Leave running: lifespan recovery resumes from the last durable checkpoint.
        raise
    except Exception as exc:
        job.update(
            status="failed",
            result={"request_id": request_id, "status": "failed", "error": type(exc).__name__},
        )
        trace(request_id, "task", "failed", error=type(exc).__name__)
    save("jobs", request_id, job)
