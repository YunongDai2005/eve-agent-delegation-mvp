from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ToolName = Literal["search_gdacs_events", "search_collections"]


class Query(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    mode: Literal["live", "mock"] = "live"
    planner: Literal["rules", "llm"] = "rules"
    fault: Literal["none", "empty", "transient", "malformed", "permanent", "timeout"] = "none"

    @field_validator("query")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Provide a nonempty Earth Observation request")
        return value.strip()

    @model_validator(mode="after")
    def no_live_fault(self) -> "Query":
        if self.mode == "live" and self.fault != "none":
            raise ValueError("Fault injection is available only in explicitly labelled mock mode")
        return self


class ToolCall(BaseModel):
    server: Literal["gdacs", "eodashboard"]
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_call(self) -> "ToolCall":
        if self.tool == "search_gdacs_events":
            if self.server != "gdacs" or set(self.arguments) - {
                "eventlist",
                "country",
                "alertlevel",
            }:
                raise ValueError("Invalid GDACS call")
            if self.arguments.get("eventlist") not in (
                None,
                "EQ",
                "TC",
                "FL",
                "VO",
                "WF",
                "DR",
                "TS",
            ):
                raise ValueError("Unsupported hazard code")
            if self.arguments.get("alertlevel") not in (None, "Green", "Orange", "Red"):
                raise ValueError("Unsupported GDACS alert level")
        elif self.server != "eodashboard" or set(self.arguments) - {"keyword", "theme", "code"}:
            raise ValueError("Invalid EO Dashboard call")
        for value in self.arguments.values():
            if value is not None and (not isinstance(value, str) or len(value) > 120):
                raise ValueError("Tool arguments must be short strings")
        return self


class Plan(BaseModel):
    accepted: bool = True
    rationale: str = Field(max_length=1000)
    calls: list[ToolCall] = Field(default_factory=list, max_length=4)
    planner: Literal["rules", "llm"] = "rules"

    @model_validator(mode="after")
    def accepted_calls(self) -> "Plan":
        if self.accepted and not self.calls:
            raise ValueError("An accepted plan must select at least one tool")
        if not self.accepted and self.calls:
            raise ValueError("Rejected plans must not execute tools")
        return self


class Delegation(BaseModel):
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    request: Query
    plan: Plan
    deadline_epoch: float | None = None
