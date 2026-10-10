"""Synthetic fixtures over REAL MCP stdio transport. Never used by live requests."""

import argparse
import asyncio
import json

from mcp.server.fastmcp import FastMCP

parser = argparse.ArgumentParser()
parser.add_argument("--fault", default="none")
args = parser.parse_args()
mcp = FastMCP("Explicit offline MOCK EVE tools")
attempts = 0


async def inject() -> str | None:
    global attempts
    attempts += 1
    if args.fault == "timeout":
        await asyncio.sleep(3)
    if args.fault == "permanent" or (args.fault == "transient" and attempts == 1):
        return json.dumps({"error": "MOCK upstream HTTP 503"})
    if args.fault == "malformed":
        return "{not valid JSON"
    if args.fault == "empty":
        return json.dumps({"error": "No results found for query."})
    return None


@mcp.tool()
async def search_gdacs_events(
    eventlist: str | None = None,
    alertlevel: str | None = None,
    country: str | None = None,
) -> str:
    fault = await inject()
    if fault:
        return fault
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [90.4, 23.7]},
                    "properties": {
                        "name": "MOCK synthetic hazard (not a real disaster)",
                        "eventtype": eventlist or "FL",
                        "country": country or "Mockland",
                        "alertlevel": alertlevel or "Orange",
                        "fromdate": "2026-10-01T00:00:00",
                        "todate": "2026-10-02T00:00:00",
                        "url": "https://example.invalid/mock-event",
                    },
                }
            ],
        }
    )


@mcp.tool()
async def search_collections(code: str = "", theme: str = "", keyword: str = "") -> str:
    fault = await inject()
    if fault:
        return fault
    return (
        "Found 1 collection(s):\n\n   MOCK-WATER\n   Title: MOCK flood water resource\n"
        "   Themes: water\n   Satellite: MOCK-SAR\n"
        "   URL: https://example.invalid/mock-collection\n"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
