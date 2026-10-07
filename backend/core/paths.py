"""Path classification and glob matching (pure)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import PurePosixPath

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
    }
)
DEFAULT_IGNORE_GLOBS = (
    "**/*.lock",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/*.snap",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/vendor/**",
    "**/__snapshots__/**",
    "**/*.generated.*",
    "**/migrations/**",
)
DOC_EXTENSIONS = frozenset({".md", ".mdx", ".rst", ".txt", ".adoc"})
CODE_EXTENSIONS = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".rb", ".rs", ".php"}
)


@lru_cache(maxsize=256)
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def path_matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(_glob_to_regex(p).match(path) for p in patterns)


def is_lockfile(path: str) -> bool:
    return PurePosixPath(path).name in LOCKFILES


def is_doc(path: str) -> bool:
    posix = PurePosixPath(path)
    return posix.suffix.lower() in DOC_EXTENSIONS or posix.parts[:1] in {("docs",), ("doc",)}


def is_test_path(path: str) -> bool:
    posix = PurePosixPath(path)
    name = posix.name
    parts = set(posix.parts[:-1])
    return (
        bool(parts & {"tests", "test", "__tests__", "spec", "specs"})
        or name.startswith("test_")
        or name.endswith("_test.py")
        or bool(re.search(r"\.(test|spec)\.[jt]sx?$", name))
    )


def is_code(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in CODE_EXTENSIONS
