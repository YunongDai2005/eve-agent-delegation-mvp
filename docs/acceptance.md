# Acceptance matrix

The **no-key real-data MVP** is validated, with separate real DeepSeek-V4.1-Flash planning
verification. This is independent work, not an ESA release.

| Required acceptance item | Result | Reproducible evidence |
|---|---|---|
| Real LangGraph execution | Passed | `evidence/last-live.json`, `/api/graph`, actual `docs/langgraph.mmd` |
| Real LLM plan through full live chain | Passed in small sample | `evidence/llm-live-deepseek-corrected.json`; initial partial run preserved separately |
| Independently discovered/called A2A Agent | Passed | Different Supervisor/Agent PIDs, discovery, delegate and tasks/get trace |
| Real MCP tool call | Passed | Official `search_gdacs_events` and `search_collections` calls in live packet |
| Real external EO-related data | Passed | GDACS GeoJSON + official EO Dashboard STAC collection URL |
| Structured results with sources | Passed | A2A DataPart, `retrieved_events`, `candidate_eo_resources`, raw results |
| Complete task trace | Passed | Task trace API and saved live/evaluation packets |
| At least one exercised error path | Passed | Live no-data case; six offline boundary/fault cases; SDK invalid input |
| Automated tests with actual run records | Passed | 27/27 pytest, 21/21 fixture case expectations, separate 2/3 live data success |
| README reproduction | Passed locally | Independent project, lock/setup scripts; clean-checkout verification record |
| Architecture matches code | Passed | Compiled graph export; actual A2A/MCP process boundaries; Mermaid SVG export |

## Explicitly incomplete or unmeasured

- General LLM quality: unmeasured. Four real-planning fixture cases and one corrected successful
  live demo are integration checks; rules metrics are not LLM metrics.
- GitHub publication: local repository prepared; no remote upload is claimed.
- Full Inspector UI/conformance suite: original structural validators were exercised only.
- Live outage recovery statistics: not measured. Mock transient recovery is separately labelled.
- Cross-platform setup: only Windows/Python 3.12 was verified.
- CDSE OAuth/image downloads, geocode execution, event-to-acquisition matching, full EVE backend,
  TheOne integration and model benchmarks are deliberately outside scope.

The raw live success rate is 2/3, not 100%. The no-match case remains documented and can be
rerun using the same query. The full-chain flood/resource demo itself succeeded.
