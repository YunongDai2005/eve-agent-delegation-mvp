"""Repeatable, separate live/mock FULL protocol-chain evaluation; no pytest stubs."""

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import run_query  # noqa: E402
from eve_demo.config import ROOT  # noqa: E402
from eve_demo.processes import Services  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--planner", choices=["rules", "llm"], default="rules")
    parser.add_argument("--cases", type=Path, default=ROOT / "tests" / "cases.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--agent-port", type=int)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.mode == "live":
        cases = [c for c in cases if c.get("live")]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        parser.error("No evaluation cases selected")
    rows = []
    with tempfile.TemporaryDirectory(prefix="eve-eval-") as directory:
        api_port = args.api_port or (9120 if args.mode == "mock" else 9160)
        agent_port = args.agent_port or (9121 if args.mode == "mock" else 9161)
        with Services(api_port, agent_port, Path(directory)) as services:
            for case in cases:
                payload = {
                    "query": case["query"],
                    "mode": args.mode,
                    "planner": args.planner,
                    "fault": case.get("fault", "none") if args.mode == "mock" else "none",
                }
                packet = run_query(services, payload, verbose=False)
                result = packet["job"]["result"]
                events = packet["trace"]
                selected = [c["tool"] for c in result.get("plan", {}).get("calls", [])]
                protocol_ok = any(e["node"] == "a2a.get_task" for e in events)
                expected = case["expected"] if args.mode == "mock" else "success"
                calls = result.get("plan", {}).get("calls", [])
                filters_ok = all(
                    any(
                        call["tool"] == constraint["tool"]
                        and all(
                            call["arguments"].get(key) == value
                            for key, value in constraint["arguments"].items()
                        )
                        for call in calls
                    )
                    for constraint in case.get("required_filters", [])
                )
                passed = (
                    result["status"] == expected
                    and sorted(selected) == sorted(case["tools"])
                    and filters_ok
                )
                recovery = any(e["node"] in {"mcp.retry", "recover"} for e in events)
                row = {
                    "id": case["id"],
                    "query": case["query"],
                    "expected": expected,
                    "observed": result["status"],
                    "passed": passed,
                    "tool_selection_correct": sorted(selected) == sorted(case["tools"]),
                    "required_filters_correct": filters_ok,
                    "delegation_eligible": bool(case["tools"]),
                    "a2a_success": protocol_ok,
                    "recovered": recovery and result["status"] == "success",
                    "latency_ms": packet["wall_latency_ms"],
                    "packet": packet,
                }
                rows.append(row)
                print(
                    f"{case['id']}: {result['status']} | expected={expected} | "
                    f"pass={passed} | {row['latency_ms']:.0f}ms",
                    flush=True,
                )
    latencies = sorted(r["latency_ms"] for r in rows)
    eligible = [r for r in rows if r["delegation_eligible"]]
    transient = [
        r for r in rows if next(c for c in cases if c["id"] == r["id"]).get("fault") == "transient"
    ]
    summary = {
        "mode": args.mode,
        "planner": args.planner,
        "model": os.getenv("OPENAI_MODEL") if args.planner == "llm" else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows),
        "case_expectation_pass_rate": sum(r["passed"] for r in rows) / len(rows),
        "task_success_rate": sum(r["observed"] == "success" for r in rows) / len(rows),
        "tool_selection_accuracy": sum(r["tool_selection_correct"] for r in rows) / len(rows),
        "a2a_delegation_success_rate": sum(r["a2a_success"] for r in eligible) / len(eligible)
        if eligible
        else None,
        "error_recovery_rate": sum(r["recovered"] for r in transient) / len(transient)
        if transient
        else None,
        "p95_latency_ms": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "mean_latency_ms": sum(latencies) / len(latencies),
        "limits": "MOCK uses synthetic MCP payloads; LIVE uses official EVE MCP and external APIs. "
        "LLM planning requires an external provider even in mock mode. "
        "Small samples are not reliability or general model-quality estimates.",
    }
    suffix = "-llm" if args.planner == "llm" else ""
    output = args.output or ROOT / "evidence" / f"evaluation-{args.mode}{suffix}.json"
    output.write_text(json.dumps({"summary": summary, "runs": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(output)
    if args.mode == "mock" and not all(r["passed"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
