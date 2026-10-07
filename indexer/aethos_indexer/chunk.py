"""Turn parsed files into the upload payload (symbols plus searchable chunks)."""

from __future__ import annotations

from typing import Any

from aethos_indexer.parse import ParsedFile, SymbolInfo
from core.lexical import identifier_tokens
from core.tokens import estimate_tokens

MAX_CHUNK_LINES = 300
MAX_FILE_CHUNK_LINES = 120
MAX_SYMBOLS_PER_FILE = 5000


def search_tokens(text: str, extra: str = "") -> str:
    tokens = sorted(identifier_tokens(f"{text}\n{extra}"))
    return " " + " ".join(tokens) + " " if tokens else " "


def _symbol_text(file: ParsedFile, symbol: SymbolInfo) -> list[str]:
    end = symbol.header_end_line if symbol.kind == "class" else symbol.end_line
    return file.lines[symbol.start_line - 1 : end]


def file_payload(file: ParsedFile) -> dict[str, Any]:
    symbols = file.symbols[:MAX_SYMBOLS_PER_FILE]
    chunks: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols):
        lines = _symbol_text(file, symbol)
        for part, start in enumerate(range(0, max(len(lines), 1), MAX_CHUNK_LINES)):
            text = "\n".join(lines[start : start + MAX_CHUNK_LINES])
            if not text.strip():
                continue
            chunks.append(
                {
                    "symbol_index": index,
                    "part": part,
                    "text": text,
                    "token_count": estimate_tokens(text),
                    "search_tokens": search_tokens(text, f"{symbol.qualified_name} {file.path}"),
                }
            )
    if not symbols:
        text = "\n".join(file.lines[:MAX_FILE_CHUNK_LINES])
        if text.strip():
            chunks.append(
                {
                    "symbol_index": None,
                    "part": 0,
                    "text": text,
                    "token_count": estimate_tokens(text),
                    "search_tokens": search_tokens(text, file.path),
                }
            )
    return {
        "path": file.path,
        "language": file.language,
        "content_hash": file.content_hash,
        "loc": file.loc,
        "is_test": file.is_test,
        "symbols": [
            {
                "name": s.name,
                "qualified_name": s.qualified_name,
                "kind": s.kind,
                "start_line": s.start_line,
                "end_line": max(s.end_line, s.start_line),
                "signature": s.signature,
                "exported": s.exported,
            }
            for s in symbols
        ],
        "chunks": chunks,
    }
