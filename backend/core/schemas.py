"""Structured LLM output contract (pure Pydantic)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NIT = "nit"


SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.NIT: 0,
}

Category = Literal["bug", "security", "performance", "maintainability", "testing", "style", "other"]


class FindingOut(BaseModel):
    path: str
    line: int = Field(ge=1)
    start_line: int | None = Field(default=None, ge=1)
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    category: Category
    title: str = Field(max_length=140)
    body: str
    suggestion: str | None = None


class WalkthroughItem(BaseModel):
    path: str
    change: str


class ReviewOutput(BaseModel):
    summary: str
    walkthrough: list[WalkthroughItem] = Field(default_factory=list)
    findings: list[FindingOut] = Field(default_factory=list)
