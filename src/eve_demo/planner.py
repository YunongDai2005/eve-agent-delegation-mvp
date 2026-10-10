import os
import re

from eve_demo.models import Plan, Query, ToolCall

HAZARDS = {
    "flood": "FL",
    "earthquake": "EQ",
    "cyclone": "TC",
    "hurricane": "TC",
    "typhoon": "TC",
    "volcano": "VO",
    "wildfire": "WF",
    "drought": "DR",
    "tsunami": "TS",
}


async def plan_request(request: Query) -> Plan:
    if request.planner == "llm":
        return await llm_plan(request.query)
    text = request.query.lower()
    hazard = next((code for word, code in HAZARDS.items() if word in text), None)
    disaster = hazard or re.search(r"\b(disaster|hazard|gdacs)\b", text)
    resources = re.search(
        r"\b(satellite|observation|resources?|stac|catalog|collections?|monitoring)\b", text
    )
    if not disaster and not resources:
        return Plan(accepted=False, rationale="Outside the supported EO/disaster retrieval skills")
    calls: list[ToolCall] = []
    if disaster:
        args: dict = {"eventlist": hazard} if hazard else {}
        country = re.search(r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", request.query)
        if country:
            args["country"] = country.group(1)
        level = next((v for v in ("Red", "Orange", "Green") if v.lower() in text), None)
        if level:
            args["alertlevel"] = level
        calls.append(ToolCall(server="gdacs", tool="search_gdacs_events", arguments=args))
    if resources:
        keyword = next((word for word in HAZARDS if word in text), "water")
        if "sentinel" in text:
            keyword = "sentinel"
        calls.append(
            ToolCall(
                server="eodashboard", tool="search_collections", arguments={"keyword": keyword}
            )
        )
    return Plan(rationale="Limited keyword routing; no LLM decision is claimed", calls=calls)


async def llm_plan(query: str) -> Plan:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        raise RuntimeError("llm planner requires OPENAI_API_KEY and OPENAI_MODEL in .env")
    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0,
        timeout=25,
        max_retries=1,
    )
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "Plan an EO/disaster request. Return ONLY JSON following this schema: "
                    + str(Plan.model_json_schema())
                    + " Use only gdacs/search_gdacs_events (eventlist EQ TC FL VO WF DR TS, "
                    "country, alertlevel Green Orange Red) and eodashboard/search_collections "
                    "(keyword, theme, code). Reject unrelated requests. Do not invent data. "
                    "Choose tools and filters from the request. Maximum four calls. planner=llm."
                )
            ),
            HumanMessage(content=query),
        ]
    )
    if not isinstance(response.content, str):
        raise ValueError("Planner returned non-text content")
    plan = Plan.model_validate_json(
        response.content.strip().removeprefix("```json").removesuffix("```")
    )
    return plan.model_copy(update={"planner": "llm"})
