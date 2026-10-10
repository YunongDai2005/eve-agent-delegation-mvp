"""Repeatable, separate live/mock FULL protocol-chain evaluation; no pytest stubs."""

import argparse
import json
import math
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
    parser.add_argument("--limit", type=int)
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--agent-port", type=int)
    args = parser.parse_args()
    cases = json.loads((ROOT / "tests" / "cases.json").read_text())
    if args.mode == "live":
        cases = [c for c in cases if c.get("live")]
    if args.limit:
        cases = cases[: args.limit]
    rows = []
    with tempfile.TemporaryDirectory(prefix="eve-eval-") as directory:
        api_port = args.api_port or (9120 if args.mode == "mock" else 9160)
        agent_port = args.agent_port or (9121 if args.mode == "mock" else 9161)
        with Services(api_port, agent_port, Path(directory)) as services:
            for case in cases:
                payload = {
                    "query": case["query"],
                    "mode": args.mode,
                    "fault": case.get("fault", "none") if args.mode == "mock" else "none",
                }
                packet = run_query(services, payload, verbose=False)
                result = packet["job"]["result"]
                events = packet["trace"]
                selected = [c["tool"] for c in result.get("plan", {}).get("calls", [])]
                protocol_ok = any(e["node"] == "a2a.get_task" for e in events)
                expected = case["expected"] if args.mode == "mock" else "success"
                passed = result["status"] == expected and sorted(selected) == sorted(case["tools"])
                recovery = any(e["node"] in {"mcp.retry", "recover"} for e in events)
                row = {
                    "id": case["id"],
                    "query": case["query"],
                    "expected": expected,
                    "observed": result["status"],
                    "passed": passed,
                    "tool_selection_correct": sorted(selected) == sorted(case["tools"]),
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
        "planner": "rules",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows),
        "case_expectation_pass_rate": sum(r["passed"] for r in rows) / len(rows),
        "task_success_rate": sum(r["observed"] == "success" for r in rows) / len(rows),
        "tool_selection_accuracy": sum(r["tool_selection_correct"] for r in rows) / len(rows),
        "a2a_delegation_success_rate": sum(r["a2a_success"] for r in eligible) / len(eligible),
        "error_recovery_rate": sum(r["recovered"] for r in transient) / len(transient)
        if transient
        else None,
        "p95_latency_ms": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "mean_latency_ms": sum(latencies) / len(latencies),
        "limits": "MOCK uses synthetic MCP payloads; LIVE uses official EVE MCP and external APIs. "
        "Neither evaluates real LLM planning. Small live samples are not reliability estimates.",
    }
    output = ROOT / "evidence" / f"evaluation-{args.mode}.json"
    output.write_text(json.dumps({"summary": summary, "runs": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(output)
    if args.mode == "mock" and not all(r["passed"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
