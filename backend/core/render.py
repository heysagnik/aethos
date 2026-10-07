"""Markdown rendering for GitHub comments (pure)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.verdict import Reason, Verdict

VERDICT_LABELS = {
    Verdict.READY: "✅ Ready to merge",
    Verdict.READY_WITH_SUGGESTIONS: "🟡 Ready to merge, with suggestions",
    Verdict.NOT_READY: "🔴 Not ready to merge",
    Verdict.INCONCLUSIVE: "⚪ Inconclusive",
}
SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "nit": "⚪"}


@dataclass(frozen=True)
class FindingView:
    path: str
    line: int
    start_line: int | None
    severity: str
    category: str
    title: str
    body: str
    suggestion: str
    inline: bool


@dataclass(frozen=True)
class SummaryView:
    verdict: Verdict
    reasons: tuple[Reason, ...]
    summary: str
    findings: tuple[FindingView, ...]
    walkthrough: tuple[tuple[str, str], ...] = ()
    blast_radius: tuple[str, ...] = ()
    footer: str = ""
    notes: list[str] = field(default_factory=list)


def _fence_for(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def inline_comment_body(finding: FindingView) -> str:
    icon = SEVERITY_ICONS.get(finding.severity, "")
    parts = [f"{icon} **{finding.severity.capitalize()}** · {finding.category}: {finding.title}"]
    parts.append(finding.body.strip())
    if finding.suggestion:
        fence = _fence_for(finding.suggestion)
        parts.append(f"{fence}suggestion\n{finding.suggestion.rstrip()}\n{fence}")
    return "\n\n".join(p for p in parts if p)


def _finding_line(finding: FindingView) -> str:
    icon = SEVERITY_ICONS.get(finding.severity, "")
    location = f"`{finding.path}:{finding.line}`"
    return f"- {icon} **{finding.title}** ({finding.category}) at {location}"


def summary_markdown(view: SummaryView) -> str:
    out = [f"## Aethos: {VERDICT_LABELS[view.verdict]}", ""]
    if view.summary.strip():
        out += [view.summary.strip(), ""]

    blocking = [r for r in view.reasons if r.blocking]
    others = [r for r in view.reasons if not r.blocking]
    if blocking:
        out += ["### Blocking", *[f"- {r.text}" for r in blocking], ""]
    if others:
        title = "### Suggestions" if view.verdict != Verdict.INCONCLUSIVE else "### Notes"
        out += [title, *[f"- {r.text}" for r in others], ""]

    bottlenecks = [f for f in view.findings if f.category == "performance"]
    if bottlenecks or view.blast_radius:
        out.append("### Bottlenecks")
        out += [_finding_line(f) for f in bottlenecks]
        out += [f"- Blast radius: {item}" for item in view.blast_radius]
        out.append("")

    detached = [f for f in view.findings if not f.inline]
    if detached:
        out += [
            "### Other findings",
            "_These could not be attached to a changed line._",
            *[f"{_finding_line(f)}\n  {f.body.strip()}" for f in detached],
            "",
        ]

    inline_count = sum(1 for f in view.findings if f.inline)
    if inline_count:
        out += [f"{inline_count} inline comment(s) on the changed lines.", ""]

    if view.walkthrough:
        out += ["<details><summary>Walkthrough</summary>", ""]
        out += [f"- `{path}`: {change}" for path, change in view.walkthrough]
        out += ["", "</details>", ""]

    for note in view.notes:
        out += [f"> {note}", ""]
    if view.footer:
        out.append(f"<sub>{view.footer}</sub>")
    return "\n".join(out).rstrip() + "\n"


def notice_markdown(title: str, detail: str) -> str:
    return f"## Aethos: {title}\n\n{detail}\n"
