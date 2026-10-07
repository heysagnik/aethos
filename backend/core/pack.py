"""Context pack assembly under a hard token budget (pure, deterministic, no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.tokens import estimate_tokens

# (section, priority). Higher priority is filled first and dropped last.
SECTIONS: tuple[tuple[str, int], ...] = (
    ("meta", 10),
    ("diff", 9),
    ("symbols", 8),
    ("related", 6),
    ("similar", 5),
    ("tests", 4),
    ("map", 3),
)
SECTION_TITLES = {
    "meta": "Pull request",
    "diff": "Changes under review (unified diff)",
    "symbols": "Enclosing code before the change (from the index of the base branch)",
    "related": "Callers and callees of the changed code",
    "similar": "Similar existing code",
    "tests": "Related tests",
    "map": "Repository map",
}
DEFAULT_SHARES: dict[str, float] = {
    "meta": 1.0,
    "diff": 0.40,
    "symbols": 0.25,
    "related": 0.15,
    "similar": 0.10,
    "tests": 0.05,
    "map": 0.05,
}


@dataclass(frozen=True)
class PackItem:
    section: str
    title: str
    text: str
    reason: str
    score: float = 0.0
    order: int = 0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass(frozen=True)
class DroppedItem:
    section: str
    title: str
    reason: str
    tokens: int


@dataclass
class ContextPack:
    budget: int
    items: list[PackItem] = field(default_factory=list)
    dropped: list[DroppedItem] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_used(self) -> int:
        return sum(item.tokens for item in self.items)

    @property
    def diff_complete(self) -> bool:
        return not any(d.section == "diff" for d in self.dropped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "tokens_used": self.tokens_used,
            "diff_complete": self.diff_complete,
            "meta": self.meta,
            "items": [
                {
                    "section": i.section,
                    "title": i.title,
                    "reason": i.reason,
                    "tokens": i.tokens,
                    "text": i.text,
                }
                for i in self.items
            ],
            "dropped": [
                {"section": d.section, "title": d.title, "reason": d.reason, "tokens": d.tokens}
                for d in self.dropped
            ],
        }


def build_pack(
    candidates: list[PackItem],
    budget: int,
    shares: dict[str, float] | None = None,
    meta: dict[str, Any] | None = None,
) -> ContextPack:
    """Select candidates by section priority within `budget` tokens.

    Pass 1 fills each section up to its share of the budget. Pass 2 hands unused budget back
    to dropped items, highest priority first. "meta" is mandatory and always included.
    """
    shares = shares or DEFAULT_SHARES
    pack = ContextPack(budget=budget, meta=dict(meta or {}))
    included: list[PackItem] = []
    dropped: list[tuple[int, PackItem, str]] = []
    total = 0

    for section, priority in SECTIONS:
        cap = int(budget * shares.get(section, 0.0))
        used = 0
        pool = sorted(
            (c for c in candidates if c.section == section),
            key=lambda c: (-c.score, c.order),
        )
        for item in pool:
            tokens = item.tokens
            if section == "meta":
                included.append(item)
                total += tokens
            elif used + tokens <= cap and total + tokens <= budget:
                included.append(item)
                used += tokens
                total += tokens
            else:
                reason = "section budget" if used + tokens > cap else "total budget"
                dropped.append((priority, item, reason))

    leftover: list[tuple[int, PackItem, str]] = []
    for priority, item, reason in sorted(dropped, key=lambda d: (-d[0], -d[1].score, d[1].order)):
        if total + item.tokens <= budget:
            included.append(item)
            total += item.tokens
        else:
            leftover.append((priority, item, reason))

    priority_of = dict(SECTIONS)
    included.sort(key=lambda i: (-priority_of[i.section], i.order))
    pack.items = included
    pack.dropped = [DroppedItem(i.section, i.title, r, i.tokens) for _, i, r in leftover]
    return pack


def render_pack(pack: ContextPack) -> str:
    """Render the pack as the user-message body for the model."""
    blocks: list[str] = []
    for section, _ in SECTIONS:
        items = [i for i in pack.items if i.section == section]
        if not items:
            continue
        blocks.append(f"# {SECTION_TITLES[section]}")
        for item in items:
            blocks.append(f"## {item.title}\n````\n{item.text}\n````")
    omitted = [d for d in pack.dropped if d.section == "diff"]
    if omitted:
        names = ", ".join(sorted({d.title for d in omitted}))
        blocks.append(
            "# Not shown\nSome changes did not fit the context budget and are NOT included: "
            f"{names}. Do not comment on code you cannot see."
        )
    return "\n\n".join(blocks)


@dataclass(frozen=True)
class SymbolRef:
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int


def symbols_overlapping(ranges: list[tuple[int, int]], symbols: list[SymbolRef]) -> list[SymbolRef]:
    """Symbols whose line span overlaps any (start, end) range, in file order."""
    hit = [
        s
        for s in symbols
        if any(s.start_line <= end and start <= s.end_line for start, end in ranges)
    ]
    return sorted(hit, key=lambda s: (s.start_line, s.end_line))
