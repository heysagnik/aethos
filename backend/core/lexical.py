"""Identifier-token similarity for finding related code without embeddings (pure)."""

from __future__ import annotations

import math
import re

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
STOP_TOKENS = frozenset(
    {
        "the",
        "and",
        "for",
        "not",
        "with",
        "this",
        "that",
        "self",
        "none",
        "true",
        "false",
        "return",
        "else",
        "elif",
        "def",
        "class",
        "import",
        "from",
        "const",
        "let",
        "var",
        "function",
        "async",
        "await",
        "null",
        "undefined",
        "new",
        "str",
        "int",
        "bool",
        "dict",
        "list",
        "len",
        "get",
        "set",
        "args",
        "kwargs",
        "try",
        "except",
        "catch",
        "finally",
        "raise",
        "throw",
        "pass",
        "lambda",
        "yield",
        "type",
        "interface",
        "export",
        "default",
    }
)
MAX_TOKENS = 64


def identifier_tokens(text: str) -> set[str]:
    """Lowercased sub-words of identifiers (camelCase and snake_case split)."""
    tokens: set[str] = set()
    for word in _WORD_RE.findall(text):
        for part in _CAMEL_RE.findall(word):
            lowered = part.lower()
            if len(lowered) >= 3 and lowered not in STOP_TOKENS:
                tokens.add(lowered)
    if len(tokens) > MAX_TOKENS:
        return set(sorted(tokens, key=lambda t: (-len(t), t))[:MAX_TOKENS])
    return tokens


def similarity(query: set[str], doc: set[str]) -> float:
    """Cosine similarity of two token sets."""
    if not query or not doc:
        return 0.0
    return len(query & doc) / math.sqrt(len(query) * len(doc))
