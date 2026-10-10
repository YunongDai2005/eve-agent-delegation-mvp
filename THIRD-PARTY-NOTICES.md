# Attribution and reuse

This is an independent portfolio demonstration. It is not an official ESA release and is not
approved or endorsed by ESA, Pi School, or the EVE maintainers.

The files `vendor/eve/gdacs/server.py` and `vendor/eve/eodashboard/server.py` are **unmodified**
snapshots of [eve-esa/mcp-tool-registry](https://github.com/eve-esa/mcp-tool-registry) at commit
`69bfcde7f80b1fc50ebd31001b56ce257c500f27`, authored by the upstream EVE team and contributors.
The original [Apache-2.0 license](vendor/eve/LICENSE) is retained. Their SHA-256 values are in
`upstreams.json`. No NOTICE file was present in the repository root at this revision.

The application imports the official Apache-2.0
[A2A Python SDK](https://github.com/a2aproject/a2a-python/tree/v0.3.25), released as
`a2a-sdk==0.3.25`, rather than copying/reimplementing its protocol. LangGraph and the MCP Python
SDK are installed packages, retaining their package licenses. `requirements.lock` lists the
installed dependency versions; individual distribution metadata supplies their licenses.

The other six requested repositories were read for research, not incorporated into the
runtime. Their versions, inspected source paths and declared licenses appear in
`upstreams.json`. TheOne is MIT licensed; no TheOne code is copied into this project.

The official A2A Inspector validator is executed from an explicitly supplied external checkout
by `scripts/verify_inspector.py`; it is not distributed here. Validation does not imply official
endorsement or a full conformance certification.

Synthetic fixtures use `example.invalid` URLs and have no relationship to real disaster reports.
Real GDACS and EO Dashboard results remain attributed to their external providers via returned
source URLs. No satellite imagery or GDACS-to-imagery match is claimed.
