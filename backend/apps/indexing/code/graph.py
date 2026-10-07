"""Resolve imports and calls into dependency edges.

Resolution is name-based (no type checker), so call edges carry a confidence below 1.0 when
the match is ambiguous or inferred from an attribute call.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

from apps.indexing.code.parse import ParsedFile, SymbolInfo

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PY_SOURCE_ROOTS = frozenset({"src", "lib", "backend", "python"})
MAX_CALL_EDGES_PER_FILE = 2000


@dataclass(frozen=True)
class EdgeOut:
    kind: str
    from_path: str
    from_symbol: str | None
    to_path: str
    to_symbol: str | None
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "from_path": self.from_path,
            "from_symbol": self.from_symbol,
            "to_path": self.to_path,
            "to_symbol": self.to_symbol,
            "confidence": self.confidence,
        }


def _python_modules(paths: set[str]) -> dict[str, str]:
    modules: dict[str, str] = {}
    for path in sorted(paths):
        if not path.endswith(".py"):
            continue
        parts = path[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        modules.setdefault(".".join(parts), path)
        if len(parts) > 1 and parts[0] in PY_SOURCE_ROOTS:
            modules.setdefault(".".join(parts[1:]), path)
    return modules


def _resolve_python(
    file: ParsedFile, imp_spec: str, level: int, names: tuple[str, ...], modules: dict[str, str]
) -> list[tuple[str, tuple[str, ...]]]:
    """Return [(target path, imported names)] for one import statement."""
    if level:
        directory = posixpath.dirname(file.path)
        for _ in range(level - 1):
            directory = posixpath.dirname(directory)
        base = directory.replace("/", ".")
        prefix = ".".join(p for p in (base, imp_spec) if p)
    else:
        prefix = imp_spec
    targets: list[tuple[str, tuple[str, ...]]] = []
    module_path = modules.get(prefix) if prefix else None
    if module_path:
        targets.append((module_path, names))
    for name in names:  # `from pkg import submodule`
        sub = modules.get(f"{prefix}.{name}" if prefix else name)
        if sub and sub != module_path:
            targets.append((sub, ()))
    return targets


def _resolve_js(file: ParsedFile, spec: str, paths: set[str]) -> str | None:
    if spec.startswith("@/"):
        candidates = [posixpath.normpath(f"src/{spec[2:]}")]
    elif spec.startswith("."):
        candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(file.path), spec))]
    else:
        return None
    for base in candidates:
        if base in paths:
            return base
        for ext in JS_EXTENSIONS:
            if base + ext in paths:
                return base + ext
        for ext in JS_EXTENSIONS:
            index = f"{base}/index{ext}"
            if index in paths:
                return index
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):  # TS projects import ./x.js for x.ts
            for ts_ext in (".ts", ".tsx"):
                if stem + ts_ext in paths:
                    return stem + ts_ext
    return None


def _top_level(symbols: list[SymbolInfo]) -> dict[str, SymbolInfo]:
    result: dict[str, SymbolInfo] = {}
    for symbol in symbols:
        if "." not in symbol.qualified_name:
            result.setdefault(symbol.name, symbol)
    return result


def build_edges(files: dict[str, ParsedFile]) -> list[EdgeOut]:
    paths = set(files)
    modules = _python_modules(paths)
    edges: dict[tuple[str, str | None, str, str | None, str], EdgeOut] = {}

    def add(edge: EdgeOut) -> None:
        key = (edge.from_path, edge.from_symbol, edge.to_path, edge.to_symbol, edge.kind)
        current = edges.get(key)
        if current is None or edge.confidence > current.confidence:
            edges[key] = edge

    imported: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for path, file in files.items():
        resolved: list[tuple[str, tuple[str, ...]]] = []
        for imp in file.imports:
            if file.language == "python":
                resolved.extend(_resolve_python(file, imp.spec, imp.level, imp.names, modules))
            else:
                target = _resolve_js(file, imp.spec, paths)
                if target:
                    resolved.append((target, imp.names))
        imported[path] = [(t, n) for t, n in resolved if t != path]
        for target, _ in imported[path]:
            add(EdgeOut("imports", path, None, target, None, 1.0))
            if file.is_test and not files[target].is_test:
                add(EdgeOut("tests", path, None, target, None, 1.0))

    top_levels = {path: _top_level(file.symbols) for path, file in files.items()}
    for path, file in files.items():
        local = top_levels[path]
        methods: dict[str, SymbolInfo] = {}
        for symbol in file.symbols:
            if symbol.kind == "method":
                methods.setdefault(symbol.name, symbol)
        explicit: dict[str, str] = {}
        module_level: list[str] = []
        for target, names in imported[path]:
            if names:
                for name in names:
                    explicit.setdefault(name, target)
            else:
                module_level.append(target)

        emitted = 0
        for call in file.calls:
            if call.caller is None or emitted >= MAX_CALL_EDGES_PER_FILE:
                continue
            match: tuple[str, str, float] | None = None
            if not call.is_attr:
                local_symbol = local.get(call.name)
                if local_symbol is not None:
                    match = (path, local_symbol.qualified_name, 1.0)
                elif call.name in explicit:
                    target_symbol = top_levels[explicit[call.name]].get(call.name)
                    if target_symbol is not None:
                        match = (explicit[call.name], target_symbol.qualified_name, 0.9)
            else:
                method = methods.get(call.name)
                if method is not None:
                    match = (path, method.qualified_name, 0.6)
                else:
                    for target in module_level:
                        target_symbol = top_levels[target].get(call.name)
                        if target_symbol is not None:
                            match = (target, target_symbol.qualified_name, 0.6)
                            break
            if match is None:
                continue
            to_path, to_symbol, confidence = match
            if to_path == path and to_symbol == call.caller:
                continue
            add(EdgeOut("calls", path, call.caller, to_path, to_symbol, confidence))
            emitted += 1
    return sorted(
        edges.values(),
        key=lambda e: (e.kind, e.from_path, e.from_symbol or "", e.to_path, e.to_symbol or ""),
    )
