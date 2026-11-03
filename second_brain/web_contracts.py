"""Bounded, strict public request contracts shared by every JSON entry point."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(default="", max_length=2000)
    q: str | None = Field(default=None, max_length=2000)
    k: int = Field(default=6, ge=1, le=12)

    @model_validator(mode="after")
    def resolve_alias(self) -> "QueryRequest":
        if self.q is not None:
            if "query" in self.model_fields_set and self.query != self.q:
                raise ValueError("query and q disagree")
            self.query = self.q
        self.query = self.query.strip()
        return self


class PlanRequest(QueryRequest):
    handles: list[dict[str, Any]] | None = Field(default=None, max_length=12)
