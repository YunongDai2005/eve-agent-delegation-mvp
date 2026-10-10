# 60–90 second technical walkthrough

Prepare the environment once using `scripts/setup.ps1` or `scripts/setup.sh`. Run live once
before recording to check upstream availability. Do not splice mock results into a live recording.

**0–15s — architecture.** “This independent demonstration adds cross-agent delegation around
Earth Observation retrieval. A LangGraph supervisor plans the request; a separate agent receives
the task through the official A2A SDK. That agent uses official EVE MCP servers to query GDACS
and the ESA/NASA/JAXA EO Dashboard catalogue.” Show `docs/architecture.svg`.

**15–25s — real interfaces.** Show `docs/langgraph.mmd`, `evidence/agent-card.json`, and
`evidence/mcp-tools.json`. “These are exported from the compiled graph, running SDK service and
actual MCP discovery, not a static simulation.”

**25–65s — actual execution.** Run:

```powershell
.\.venv\Scripts\python.exe demo.py --mode live
```

“This run uses the explicitly labelled no-key rules planner. An optional LLM mode was separately
verified with DeepSeek-V4.1-Flash. Notice the two different process IDs, Agent
Card discovery, A2A delegation and tasks/get, MCP tool calls, and their timings. The returned
event dates and source links come from the upstream response. These catalogue resources are
candidates; we have not verified matching satellite acquisitions for this disaster.”

**65–80s — evidence and reliability.** Open `evidence/last-live.json`: show raw data, source
URLs and trace. “SQLite persists the task and graph checkpoints. We tested interrupted
supervisor recovery and bounded error handling. Mock and live evaluation results are reported
separately, with small live samples explicitly labelled.”

**80–90s — reproducibility.** Show README commands. “Reviewers can run the offline fixture demo
without any credentials. It still uses separate processes and real A2A/MCP transports, but the
data is clearly marked synthetic.”

## Alternatives for a network outage

Run `demo.py --mode mock`, visibly keeping the `MOCK / SYNTHETIC DATA` banner. Show the saved
live evidence packet with its timestamp as a previous captured run, never as current execution.
For recovery, run `demo.py --mode mock --fault transient`; the trace shows the first error and
second successful MCP attempt. Keep `--serve` to inspect Swagger or an external A2A Inspector.

For a real-model walkthrough, configure your own key in `.env` and add `--planner llm`.
Open `evidence/llm-live-deepseek-corrected.json` for the saved 21.69-second successful run.
Keep the model-backed four-case sample separate from the 21-case rules fixture evaluation.
