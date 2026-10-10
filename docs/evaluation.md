# Evaluation — actual runs, separate evidence classes

Environment: Windows, Python 3.12, locked dependencies. Run date: **2026-10-10 (Asia/Shanghai)**.
All reported planning uses the explicitly labelled **rules** router. Real LLM planning was
not exercised and no model decision quality is inferred from these results.

## End-to-end metrics

| Measure | Offline MOCK, 21 cases | LIVE external APIs, 3 cases |
|---|---:|---:|
| Case expectations met | 21/21 (100%) | 2/3 (66.7%) |
| Task status `success` | 16/21 (76.2%) | 2/3 (66.7%) |
| Tool selection accuracy | 21/21 (100%) | 3/3 (100%) |
| A2A delegation round trip | 20/20 (100%) | 3/3 (100%) |
| Injected transient recovery | 1/1 (100%) | Not measured |
| Mean request-to-terminal latency | 4.140 s | 11.803 s |
| P95 latency (nearest rank) | 6.042 s | 16.951 s |

These are the outputs of [mock evaluation JSON](../evidence/evaluation-mock.json) and
[live evaluation JSON](../evidence/evaluation-live.json), with per-case packets/raw tool
outputs/trace included. Text run logs are alongside them. **Three live cases do not establish
a reliability estimate**; P95 at n=3 is just the maximum observed latency. Concurrent local
check runs can affect timings. The evaluation excludes service startup but includes API
submission, polling, A2A discovery/roundtrip, MCP process startup/calls and result assembly.

Case expectation rate compares the final status AND selected tools against the case oracle.
Raw task success counts only `success`, so expected failures/rejection/no-data reduce that
metric even when handling is correct. A2A success means the remote Task was successfully
submitted and fetched, including tasks ending `failed`; it does not mean the external query
succeeded. The out-of-scope fixture does not require delegation and is excluded from that
denominator. Transient recovery is measured only on the deliberately injected 503 fixture.

## Live observations

1. Recent global GDACS flood search: **success**, 8.931 s.
2. Recent flood + EO resource search: **success**, 16.951 s. Official tools returned flood
   evidence and the EO Dashboard `alos2_floods` STAC collection candidate.
3. `Search water STAC collections`: **no_data**, 9.525 s. The official catalogue keyword search
   returned no matching collections. The system reported this honestly, without fabricated
   resources. This meets the unavailable-data behavior but **fails the case's expected data
   retrieval success**; it remains in the live denominator and is not quietly replaced.

A separate recorded full demo finished in **16.22 s**. See
[last-live.json](../evidence/last-live.json) and [terminal run](../evidence/demo-live.txt).
It retrieved an India flood report with end date 2026-10-03, plus a China flood ending 2026-09-27,
both within the declared 30-day recent window. The candidate collection is not spatially or
temporally matched to either event. The full upstream GeoJSON is preserved in `raw_output`.

## Automated and protocol checks

- **27 pytest tests passed**, including 21 full mock protocol-chain cases. Additional checks:
  API input validation/404s, argument schema enforcement, redaction, GDACS filtering/sorting,
  independent official A2A client failure submission/retrieval, and supervisor crash/resume.
  [JUnit record](../evidence/pytest.xml), [console](../evidence/pytest.txt).
- Six fixture boundary/error cases: unrelated request, no results, transient 503, malformed
  JSON, permanent 503, and timeout. The latter three end `failed` with empty evidence.
  These are actual MCP transport calls to a synthetic fixture server, not real provider outages.
- Supervisor process was terminated while delegation was in progress. After restart, SQLite
  restored the checkpoint, the final task succeeded, and only one successful planning node
  appeared in the trace. [Recovery packet](../evidence/checkpoint-recovery.json).
- A **fresh local Git clone and new virtual environment** installed using the README setup
  script. Mock full-chain execution succeeded in 4.40 s; live flood/resource execution succeeded
  in 13.34 s. [Reproduction record](../evidence/reproduction.json),
  [setup log](../evidence/clean-setup.txt), [clean live packet](../evidence/clean-live.json),
  [clean mock packet](../evidence/clean-mock.json). These extra runs are separate from the
  three-case live evaluation denominator. All eight upstream workspaces stayed clean; official
  MCP snapshot hashes matched in both original and cloned projects.
- Official A2A Inspector's **original structural validators** returned zero Agent Card and
  Task errors. The actual live Task was fetched from SQLite after a service restart via an
  independent SDK client. [Validation record](../evidence/inspector-validation.json).
  No full conformance/GUI result is claimed.
- Real-model planning without configuration was exercised and returned explicit
  `failed / RuntimeError`, without falling back to rules or synthetic evidence.
  [Missing-configuration packet](../evidence/llm-unconfigured.json). This verifies the missing-key
  path only, not real model behavior.
- Ruff, formatting, mypy and `pip check` records are in `evidence/checks.txt`.

## Known compatibility and execution limits

The first resolver attempt rejected checkpoint-sqlite 3.0.1 with LangGraph 1.2.14; 3.1.1 is
the compatible installed release. Original MCP servers emit a benign pydantic-settings
`lifespan` forward-reference warning in this locked environment; actual tool discovery and
calls succeeded. No upstream files were changed to suppress it.

An initial mock evaluation completed its 21 case assertions but failed temporary-directory
cleanup because a Windows MCP descendant still held an inherited log handle. The launcher
now cleans up only its owned process tree; the reported rerun exited successfully. This
initial run is not counted as the published evaluation result.

No model credentials were supplied. The optional real planner is implemented but requires
provider-backed verification. No CDSE OAuth, imagery download, acquisition matching, EO image
processing, geocoding, model benchmarking/evalkit scores, or large-scale deployment is claimed.
The selected tools/filters are evaluated on a small English rules-router suite, not arbitrary
natural language. No live transient recovery rate is available: a no-data response is not a
network fault. Windows is the tested platform; Linux/macOS instructions are unverified.
