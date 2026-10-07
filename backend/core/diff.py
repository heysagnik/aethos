"""Unified diff parsing and the commentable-lines map (pure)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

LineKind = Literal["add", "del", "ctx"]
FileStatus = Literal["added", "modified", "deleted", "renamed"]

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class DiffParseError(ValueError):
    """Raised when a diff cannot be parsed."""


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    old_line: int | None
    new_line: int | None
    text: str


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: tuple[DiffLine, ...]

    @property
    def old_range(self) -> tuple[int, int]:
        """Inclusive range of old-side lines touched or surrounded by this hunk."""
        return (self.old_start, max(self.old_start, self.old_start + self.old_count - 1))

    def render(self) -> str:
        prefix = {"add": "+", "del": "-", "ctx": " "}
        body = "\n".join(f"{prefix[line.kind]}{line.text}" for line in self.lines)
        return f"{self.header}\n{body}"


@dataclass(frozen=True)
class FileDiff:
    path: str
    old_path: str | None
    status: FileStatus
    hunks: tuple[Hunk, ...]
    is_binary: bool = False

    @property
    def commentable_lines(self) -> frozenset[int]:
        """New-side line numbers GitHub accepts review comments on."""
        return frozenset(
            line.new_line
            for hunk in self.hunks
            for line in hunk.lines
            if line.new_line is not None and line.kind in ("add", "ctx")
        )

    @property
    def added_line_count(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "add")

    @property
    def removed_line_count(self) -> int:
        return sum(1 for h in self.hunks for line in h.lines if line.kind == "del")

    @property
    def changed_line_count(self) -> int:
        return self.added_line_count + self.removed_line_count


def _strip_prefix(path: str, prefix: str) -> str:
    return path[len(prefix) :] if path.startswith(prefix) else path


def _parse_hunk(lines: list[str], start: int) -> tuple[Hunk, int]:
    header = lines[start]
    match = _HUNK_RE.match(header)
    if match is None:
        raise DiffParseError(f"Malformed hunk header: {header!r}")
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) is not None else 1

    parsed: list[DiffLine] = []
    old_line, new_line = old_start, new_start
    old_seen = new_seen = 0
    i = start + 1
    while i < len(lines) and (old_seen < old_count or new_seen < new_count):
        raw = lines[i]
        if raw.startswith("\\"):  # "\ No newline at end of file"
            i += 1
            continue
        marker, text = (raw[:1], raw[1:]) if raw else (" ", "")
        if marker == "+":
            parsed.append(DiffLine("add", None, new_line, text))
            new_line += 1
            new_seen += 1
        elif marker == "-":
            parsed.append(DiffLine("del", old_line, None, text))
            old_line += 1
            old_seen += 1
        elif marker == " ":
            parsed.append(DiffLine("ctx", old_line, new_line, text))
            old_line += 1
            new_line += 1
            old_seen += 1
            new_seen += 1
        else:
            raise DiffParseError(f"Unexpected diff line inside hunk: {raw!r}")
        i += 1
    while i < len(lines) and lines[i].startswith("\\"):
        i += 1
    hunk = Hunk(old_start, old_count, new_start, new_count, header, tuple(parsed))
    return hunk, i


def _split_files(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return blocks


def _parse_file_block(block: list[str]) -> FileDiff:
    header = block[0]
    old_path: str | None = None
    new_path: str | None = None
    status: FileStatus = "modified"
    is_binary = False
    hunks: list[Hunk] = []
    rename_from: str | None = None
    rename_to: str | None = None

    i = 1
    while i < len(block):
        line = block[i]
        if line.startswith("new file mode"):
            status = "added"
        elif line.startswith("deleted file mode"):
            status = "deleted"
        elif line.startswith("rename from "):
            rename_from = line[len("rename from ") :]
            status = "renamed"
        elif line.startswith("rename to "):
            rename_to = line[len("rename to ") :]
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            is_binary = True
        elif line.startswith("--- "):
            target = line[4:].split("\t")[0]
            old_path = None if target == "/dev/null" else _strip_prefix(target, "a/")
        elif line.startswith("+++ "):
            target = line[4:].split("\t")[0]
            new_path = None if target == "/dev/null" else _strip_prefix(target, "b/")
        elif line.startswith("@@"):
            hunk, i = _parse_hunk(block, i)
            hunks.append(hunk)
            continue
        i += 1

    path = new_path or rename_to or old_path
    if path is None:
        match = re.match(r"^diff --git a/(.+) b/(.+)$", header)
        if match is None:
            raise DiffParseError(f"Cannot determine path from header: {header!r}")
        path = match.group(2)
    previous = old_path or rename_from
    return FileDiff(
        path=path,
        old_path=previous if previous != path else None,
        status=status,
        hunks=tuple(hunks),
        is_binary=is_binary,
    )


def parse_unified_diff(text: str) -> list[FileDiff]:
    """Parse the output of `git diff` / GitHub's diff media type."""
    return [_parse_file_block(block) for block in _split_files(text)]
