"""Per-repository review settings: defaults < dashboard settings < `.aethos.yml`."""

from __future__ import annotations

import logging
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from core.schemas import Severity
from core.triage import TriageConfig
from core.verdict import VerdictConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = ".aethos.yml"


class ReviewSettings(BaseModel):
    enabled: bool = True
    mode: Literal["aethos", "baseline"] = "aethos"
    pack_tokens: int = Field(default=12000, ge=2000, le=100_000)
    baseline_pack_tokens: int = Field(default=60000, ge=2000, le=200_000)
    max_comments: int = Field(default=15, ge=1, le=50)
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    max_changed_lines: int = Field(default=3000, ge=100, le=20_000)
    fan_in_threshold: int = Field(default=5, ge=2, le=100)
    ignore_paths: list[str] = Field(default_factory=list, max_length=100)
    high_risk_paths: list[str] = Field(default_factory=list, max_length=100)
    block_on: list[Severity] = Field(default_factory=lambda: [Severity.CRITICAL, Severity.HIGH])

    def triage_config(self) -> TriageConfig:
        return TriageConfig(
            ignore_paths=tuple(self.ignore_paths),
            high_risk_paths=tuple(self.high_risk_paths),
            max_changed_lines=self.max_changed_lines,
        )

    def verdict_config(self) -> VerdictConfig:
        return VerdictConfig(block_on=frozenset(self.block_on))


def _flatten_yaml(raw: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    review = raw.get("review") or {}
    budget = raw.get("budget") or {}
    verdict = raw.get("verdict") or {}
    for key in ("max_comments", "min_confidence", "ignore_paths", "high_risk_paths"):
        if key in review:
            flat[key] = review[key]
    if "pack_tokens" in budget:
        flat["pack_tokens"] = budget["pack_tokens"]
    if "block_on" in verdict:
        flat["block_on"] = verdict["block_on"]
    return flat


def parse_yaml_overrides(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        logger.warning("Ignoring invalid %s", CONFIG_FILE)
        return {}
    return _flatten_yaml(raw) if isinstance(raw, dict) else {}


def resolve_settings(repo_settings: dict[str, Any], yaml_text: str | None = None) -> ReviewSettings:
    """Merge layers; a layer that fails validation is dropped rather than breaking reviews."""
    layers = [repo_settings or {}, parse_yaml_overrides(yaml_text)]
    merged: dict[str, Any] = {}
    for layer in layers:
        candidate = {**merged, **layer}
        try:
            ReviewSettings.model_validate(candidate)
        except ValidationError:
            logger.warning("Ignoring invalid review settings layer")
            continue
        merged = candidate
    return ReviewSettings.model_validate(merged)
