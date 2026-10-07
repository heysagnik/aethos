"""Merge-readiness verdict computed from structured signals (pure).

The LLM never decides the verdict. It supplies findings; this module combines them with
objective repository signals so every verdict is explainable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from core.schemas import SEVERITY_RANK, Severity


class Verdict(StrEnum):
    READY = "ready"
    READY_WITH_SUGGESTIONS = "ready_with_suggestions"
    NOT_READY = "not_ready"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class FindingSignal:
    severity: Severity
    confidence: float
    category: str
    title: str


@dataclass(frozen=True)
class VerdictConfig:
    block_on: frozenset[Severity] = frozenset({Severity.CRITICAL, Severity.HIGH})
    block_min_confidence: float = 0.7
    min_lines_for_tests: int = 20


@dataclass(frozen=True)
class VerdictInputs:
    findings: tuple[FindingSignal, ...] = ()
    is_draft: bool = False
    mergeable: bool | None = None
    ci_state: str = "unknown"  # success | failure | pending | none | unknown
    source_lines_changed: int = 0
    tests_changed: bool = False
    high_fan_in: tuple[str, ...] = ()
    coverage_complete: bool = True
    llm_ok: bool = True


@dataclass(frozen=True)
class Reason:
    code: str
    text: str
    blocking: bool


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    reasons: tuple[Reason, ...] = field(default_factory=tuple)


def _is_blocking(finding: FindingSignal, config: VerdictConfig) -> bool:
    return finding.severity in config.block_on and finding.confidence >= config.block_min_confidence


def compute_verdict(inputs: VerdictInputs, config: VerdictConfig | None = None) -> VerdictResult:
    config = config or VerdictConfig()
    blockers: list[Reason] = []
    suggestions: list[Reason] = []

    if inputs.is_draft:
        blockers.append(Reason("draft", "The pull request is still a draft.", True))
    if inputs.mergeable is False:
        blockers.append(Reason("conflicts", "The branch has merge conflicts.", True))
    if inputs.ci_state == "failure":
        blockers.append(Reason("ci_failing", "CI checks are failing.", True))
    elif inputs.ci_state == "pending":
        suggestions.append(Reason("ci_pending", "CI checks are still running.", False))

    for finding in inputs.findings:
        if _is_blocking(finding, config):
            blockers.append(
                Reason("blocking_finding", f"[{finding.severity}] {finding.title}", True)
            )
        elif SEVERITY_RANK[finding.severity] >= SEVERITY_RANK[Severity.MEDIUM] or (
            finding.severity in config.block_on
        ):
            suggestions.append(Reason("finding", f"[{finding.severity}] {finding.title}", False))

    if inputs.source_lines_changed >= config.min_lines_for_tests and not inputs.tests_changed:
        suggestions.append(
            Reason("no_tests", "Source changed without any accompanying test changes.", False)
        )
    if inputs.high_fan_in:
        names = ", ".join(inputs.high_fan_in[:5])
        suggestions.append(
            Reason("high_fan_in", f"Changes widely used code: {names}. Check dependents.", False)
        )

    if blockers:
        return VerdictResult(Verdict.NOT_READY, tuple(blockers + suggestions))
    if not inputs.llm_ok:
        reason = Reason("llm_unavailable", "The automated review could not be completed.", False)
        return VerdictResult(Verdict.INCONCLUSIVE, (reason, *suggestions))
    if not inputs.coverage_complete:
        reason = Reason(
            "partial_coverage",
            "Part of the diff did not fit the context budget and was not reviewed.",
            False,
        )
        return VerdictResult(Verdict.INCONCLUSIVE, (reason, *suggestions))
    if suggestions:
        return VerdictResult(Verdict.READY_WITH_SUGGESTIONS, tuple(suggestions))
    return VerdictResult(
        Verdict.READY, (Reason("clean", "No blocking issues or notable concerns found.", False),)
    )
