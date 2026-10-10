# Proposal-ready project summary

I built an independent Earth Observation delegation demo to demonstrate the integration
skills relevant to EVE: LangGraph orchestration, the official A2A Python SDK, and the official
EVE MCP tool registry. A supervisor plans a request and delegates retrieval to a separate
Python service through A2A JSON-RPC. The retrieval agent discovers MCP tools and queries
GDACS disaster events and the ESA/NASA/JAXA EO Dashboard catalogue.

The recorded live demonstration completed in approximately 16 seconds and returned source-linked
flood evidence plus a candidate EO collection. Results distinguish retrieved facts, catalogue
candidates, and monitoring guidance; they do not claim verified satellite imagery for an event.
The default no-key workflow uses a clearly labelled rules planner. DeepSeek-V4.1-Flash planning
was separately verified through the complete live chain and four small planning cases.

SQLite checkpoints support supervisor recovery, while structured traces expose delegation,
tool calls, timings, failures, and sources. Twenty-seven automated tests passed. Twenty-one
offline cases met their expectations; separate live evaluation retrieved data for two of
three cases and honestly reported no matches for the third. The repository includes locked
dependencies, one-command demos, exported architecture diagrams, and reproducible evidence.
