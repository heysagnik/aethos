"""Decide whether a PR is worth reviewing and how risky it looks (pure)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from core.diff import FileDiff
from core.paths import (
    DEFAULT_IGNORE_GLOBS,
    is_code,
    is_doc,
    is_lockfile,
    is_test_path,
    path_matches,
)


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TriageConfig:
    ignore_paths: tuple[str, ...] = ()
    high_risk_paths: tuple[str, ...] = ()
    max_changed_lines: int = 3000


@dataclass(frozen=True)
class TriageResult:
    skip: bool
    reason: str | None
    risk: Risk
    reviewable: tuple[FileDiff, ...] = field(default_factory=tuple)
    changed_lines: int = 0


def is_bot(login: str, account_type: str) -> bool:
    return account_type == "Bot" or login.endswith("[bot]")


def reviewable_files(files: list[FileDiff], config: TriageConfig) -> list[FileDiff]:
    ignore = DEFAULT_IGNORE_GLOBS + config.ignore_paths
    return [
        f
        for f in files
        if not f.is_binary
        and f.status != "deleted"
        and f.hunks
        and not is_lockfile(f.path)
        and not path_matches(f.path, ignore)
    ]


def _risk(files: list[FileDiff], changed: int, config: TriageConfig) -> Risk:
    score = 0
    if changed > 400:
        score += 2
    elif changed > 120:
        score += 1
    if len(files) > 15:
        score += 1
    if any(path_matches(f.path, config.high_risk_paths) for f in files):
        score += 2
    source = [f for f in files if is_code(f.path) and not is_test_path(f.path)]
    if source and not any(is_test_path(f.path) for f in files) and changed > 60:
        score += 1
    if score >= 3:
        return Risk.HIGH
    return Risk.MEDIUM if score >= 1 else Risk.LOW


def triage(
    files: list[FileDiff],
    *,
    author_login: str,
    author_type: str,
    config: TriageConfig,
) -> TriageResult:
    if is_bot(author_login, author_type):
        return TriageResult(True, "PR author is a bot", Risk.LOW)

    reviewable = reviewable_files(files, config)
    if not reviewable:
        return TriageResult(
            True, "No reviewable changes (lockfiles, generated or binary only)", Risk.LOW
        )
    if all(is_doc(f.path) for f in reviewable):
        return TriageResult(True, "Documentation-only change", Risk.LOW)

    changed = sum(f.changed_line_count for f in reviewable)
    if changed == 0:
        return TriageResult(True, "No added or removed lines", Risk.LOW)
    if changed > config.max_changed_lines:
        return TriageResult(
            True,
            f"Change is too large to review at once ({changed} lines). "
            "Split the PR or narrow it down.",
            Risk.HIGH,
            tuple(reviewable),
            changed,
        )
    return TriageResult(False, None, _risk(reviewable, changed, config), tuple(reviewable), changed)
