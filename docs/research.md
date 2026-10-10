# Phase 1: source research and implementation choice

All eight requested repositories were cloned read-only for source inspection. No upstream checkout
was modified. `upstreams.json` records exact revisions, inspected files and reuse decisions.

## Interfaces selected

- **LangGraph**: `StateGraph` with `plan`, `delegate`, `recover`, `synthesize`; async SQLite
  checkpoints keyed by an independent request/thread UUID. No new ReAct loop is implemented.
- **A2A**: official `a2a-sdk==0.3.25`, JSON-RPC protocol 0.3, SDK AgentCard at
  `/.well-known/agent-card.json`, official `ClientFactory`, `message/send` and `tasks/get`,
  official `DefaultRequestHandler`, `TaskUpdater`, `DataPart` artifacts. The latest source branch
  uses 1.0/protobuf types and incompatible AgentCard/TaskState names, so it is deliberately not
  installed. SDK source at release tag v0.3.25 was inspected as well as current samples.
- **MCP**: official `mcp==1.27.0`, `ClientSession`, `stdio_client`, `initialize`, `list_tools`,
  `call_tool`. Unmodified Apache-2.0 EVE server snapshots are included with hashes and license.
  Both GDACS and EO Dashboard require explicit `--transport stdio` despite README examples.
- **GDACS**: `search_gdacs_events(eventlist, alertlevel, country)` returns JSON GeoJSON or a
  JSON `error` object. The latter can arrive with MCP `isError=False`; the client must parse it.
  No-key HTTPS search endpoint is the one used in the official source.
- **EO Dashboard**: `search_collections(keyword, theme, code)` returns human-readable text with
  STAC URLs. The parser preserves the raw response and extracts candidate URLs. It performs
  no spatial/temporal event-to-imagery matching. `search_narratives` eagerly fetches every
  narrative in its cache loader; collection search has a smaller first-query dependency surface.
- **Geocode**: inspected `geocode_place` / `reverse_geocode_place`; not invoked by the base flow
  because GDACS already supplies point coordinates. Nominatim policy/rate limits would need
  deliberate treatment before adding repeated geocoding. CDSE OAuth remains optional.

## Reuse boundaries

EVE `agents/graphs/react/graph.py` already implements the model/tool loop and model fallback.
This MVP adds delegation *above* retrieval rather than recreating that loop. It uses a finite,
validated tool plan; an optional real model chooses tools and filters in the planning node.
The no-key rules router is explicitly limited and is not called an LLM agent.

Backend `src/services/agents/core/runner.py` integrates MongoDB, history, authentication, SSE,
custom model infrastructure and shared MCP loading. Reusing the entire runner would pull in
the full platform; only its separation of graph execution, tool errors and trace data informs
this independent implementation. `evalkit/evaluate.py` and summarization utilities target
model benchmarks/LLM judges rather than protocol-chain reliability; they are studied but not
installed (no model training dependencies, wandb, or benchmark claims).

TheOne `threads.mjs` and `topic-tools.mjs` were inspected for routing, recovery and redaction
conventions. No TheOne code or deep integration is used.

Inspector `backend/validators.py` can validate 0.3 and 1.0 objects; it is invoked unchanged by
the independent verification script. This is structural Inspector validation, not a claim of
passing a full protocol conformance suite or GUI session.

## Compatibility evidence

The resolver rejected SQLite checkpoint **3.0.1** with LangGraph **1.2.14**: it requires
checkpoint `<4`, whereas this LangGraph requires checkpoint `>=4.1,<5`. SQLite checkpoint
**3.1.1** supports that generation. The final installed combination, including transitive
dependencies, is frozen in `requirements.lock`; `pip check`, pytest, Ruff and mypy run records
are saved separately. Python 3.12 on Windows is the validated environment.

## Directory structure

```text
demo.py                  terminal live/mock demo and service launcher
src/eve_demo/            graph, API, A2A service/client, MCP client, fixtures, SQLite stores
vendor/eve/              unmodified official GDACS and EO Dashboard MCP servers + LICENSE
tests/                   unit/integration checks and 21 reusable evaluation cases
scripts/                 setup, separate live/mock evaluation, Inspector verification
docs/                    architecture, graph export, research, evaluation, demo, proposal
evidence/                actual run packets, raw responses, trace and check records
runtime/                 ignored SQLite checkpoint/task/trace files and service logs
```
