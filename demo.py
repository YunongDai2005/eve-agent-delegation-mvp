"""One command starts separate Supervisor/A2A processes and prints actual execution trace."""

import argparse
import json
import time
from pathlib import Path

import httpx

from eve_demo.config import ROOT, TOTAL_TIMEOUT
from eve_demo.processes import Services

DEFAULT_QUERY = (
    "Find a recent flood event reported by GDACS, identify relevant Earth Observation "
    "data resources, and explain how they could support flood monitoring."
)


def run_query(services: Services, payload: dict, verbose: bool = True) -> dict:
    start = time.perf_counter()
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.post(services.api_url + "/api/query", json=payload)
        response.raise_for_status()
        task_id = response.json()["task_id"]
        if verbose:
            print(f"\nRequest/thread: {task_id}", flush=True)
        count = 0
        deadline = time.monotonic() + TOTAL_TIMEOUT + 15
        while time.monotonic() < deadline:
            job = client.get(services.api_url + f"/api/tasks/{task_id}").json()
            events = client.get(services.api_url + f"/api/tasks/{task_id}/trace").json()["events"]
            if verbose:
                for event in events[count:]:
                    label = event.get("tool", event.get("agent", ""))
                    timing = f" {event['duration_ms']:.0f}ms" if "duration_ms" in event else ""
                    print(
                        f"  {event['node']:20} {event['status']:12} {label}{timing} "
                        f"pid={event['pid']}",
                        flush=True,
                    )
            count = len(events)
            if job["status"] not in {"queued", "running"}:
                return {
                    "job": job,
                    "trace": events,
                    "wall_latency_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            time.sleep(0.15)
    raise TimeoutError("Demo exceeded its total deadline")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "mock"], default="live")
    parser.add_argument("--planner", choices=["rules", "llm"], default="rules")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--fault",
        choices=["none", "empty", "transient", "malformed", "permanent", "timeout"],
        default="none",
    )
    parser.add_argument("--api-port", type=int, default=9100)
    parser.add_argument("--agent-port", type=int, default=9101)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--serve", action="store_true", help="Keep API and agent running for Swagger/Inspector"
    )
    args = parser.parse_args()
    print(f"EVE Delegation Demo | {args.mode.upper()} | planner={args.planner}", flush=True)
    if args.mode == "mock":
        print("SYNTHETIC DATA. Real LangGraph, cross-process A2A and MCP protocols.", flush=True)
    if args.planner == "rules":
        print("No-key limited rules router. No real LLM execution is claimed.", flush=True)
    query = input("EO request: ").strip() if args.interactive else args.query
    with Services(args.api_port, args.agent_port) as services:
        print(
            f"Swagger: {services.api_url}/docs | Agent Card: "
            f"{services.agent_url}/.well-known/agent-card.json",
            flush=True,
        )
        with httpx.Client(trust_env=False) as client:
            graph = client.get(services.api_url + "/api/graph").json()
            card = client.get(services.agent_url + "/.well-known/agent-card.json").json()
        packet = run_query(
            services,
            {"query": query, "mode": args.mode, "planner": args.planner, "fault": args.fault},
        )
        packet.update(agent_card=card, graph=graph, request=query)
        result = packet["job"].get("result") or {}
        print(f"\nRESULT: {result.get('status')} | {packet['wall_latency_ms'] / 1000:.2f}s")
        for event in result.get("retrieved_events", []):
            props = event["properties"]
            print(
                f"  EVENT: {props.get('name', props.get('country'))} | "
                f"{props.get('todate')}\n  SOURCE: {event['source_url']}"
            )
        for resource in result.get("candidate_eo_resources", [])[:4]:
            print(f"  CANDIDATE (event match unverified): {resource['source_url']}")
        for suggestion in result.get("analysis_suggestions", []):
            print("  GUIDANCE: " + suggestion["text"])
        for warning in result.get("warnings", []):
            print("  WARNING: " + warning)
        if result.get("error"):
            print("  ERROR: " + result["error"])
        output = args.output or ROOT / "evidence" / f"last-{args.mode}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull artifacts, raw data, sources and trace: {output}", flush=True)
        if args.serve:
            print("Services remain available. Press Ctrl+C to stop.", flush=True)
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
