"""Tree-sitter parsing of Python, JavaScript and TypeScript into symbols, imports and calls."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from core.paths import is_test_path

MAX_SIGNATURE_CHARS = 300
MAX_CLASS_HEADER_LINES = 40

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    qualified_name: str
    kind: str  # function | method | class | interface
    start_line: int  # 1-based, inclusive
    end_line: int
    signature: str
    exported: bool
    header_end_line: int  # last line of the text that represents this symbol in search


@dataclass(frozen=True)
class CallInfo:
    caller: str | None  # qualified name of the enclosing symbol, None at module level
    name: str
    is_attr: bool


@dataclass(frozen=True)
class ImportInfo:
    spec: str  # module path ("a.b", "./x", "react")
    names: tuple[str, ...] = ()
    level: int = 0  # python relative import depth


@dataclass
class ParsedFile:
    path: str
    language: str
    content_hash: str
    lines: list[str]
    symbols: list[SymbolInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    is_test: bool = False

    @property
    def loc(self) -> int:
        return len(self.lines)


_LANGUAGES: dict[str, Language] = {}
_PARSERS: dict[str, Parser] = {}


def language_for(path: str) -> str | None:
    return EXTENSION_LANGUAGE.get(PurePosixPath(path).suffix.lower())


def _parser(language: str) -> Parser:
    if language not in _PARSERS:
        if language == "python":
            lang = Language(tree_sitter_python.language())
        elif language == "javascript":
            lang = Language(tree_sitter_javascript.language())
        elif language == "typescript":
            lang = Language(tree_sitter_typescript.language_typescript())
        elif language == "tsx":
            lang = Language(tree_sitter_typescript.language_tsx())
        else:
            raise ValueError(f"Unsupported language: {language}")
        _LANGUAGES[language] = lang
        _PARSERS[language] = Parser(lang)
    return _PARSERS[language]


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def _line(node: Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: Node) -> int:
    row, col = node.end_point
    return row + 1 if col > 0 else max(row, 1)


def _signature(source: bytes, node: Node, body: Node | None) -> str:
    end = body.start_byte if body is not None else node.end_byte
    raw = source[node.start_byte : end].decode("utf-8", errors="replace")
    collapsed = " ".join(raw.split()).rstrip(":{ ").strip()
    return collapsed[:MAX_SIGNATURE_CHARS]


class _Walker:
    def __init__(self, source: bytes, language: str) -> None:
        self.source = source
        self.language = language
        self.symbols: list[SymbolInfo] = []
        self.calls: list[CallInfo] = []
        self.imports: list[ImportInfo] = []

    # -- shared -------------------------------------------------------------
    def add_symbol(
        self,
        node: Node,
        name: str,
        scope: list[str],
        kind: str,
        body: Node | None,
        exported: bool,
        header_end: int | None = None,
    ) -> str:
        qualified = ".".join([*scope, name])
        self.symbols.append(
            SymbolInfo(
                name=name,
                qualified_name=qualified,
                kind=kind,
                start_line=_line(node),
                end_line=_end_line(node),
                signature=_signature(self.source, node, body),
                exported=exported,
                header_end_line=header_end or _end_line(node),
            )
        )
        return qualified

    def visit_children(
        self,
        node: Node,
        scope: list[str],
        caller: str | None,
        in_class: bool,
        exported: bool = False,
    ) -> None:
        for child in node.children:
            self.visit(child, scope, caller, in_class, exported)

    def visit(
        self,
        node: Node,
        scope: list[str],
        caller: str | None,
        in_class: bool,
        exported: bool = False,
    ) -> None:
        if self.language == "python":
            self.visit_python(node, scope, caller, in_class)
        else:
            self.visit_js(node, scope, caller, in_class, exported)

    # -- python -------------------------------------------------------------
    def visit_python(
        self, node: Node, scope: list[str], caller: str | None, in_class: bool
    ) -> None:
        kind = node.type
        if kind == "function_definition":
            name = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            qualified = self.add_symbol(
                node,
                name,
                scope,
                "method" if in_class else "function",
                body,
                exported=not name.startswith("_") and (not scope or in_class),
            )
            if body is not None:
                self.visit_children(body, [*scope, name], qualified, False)
            return
        if kind == "class_definition":
            name = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            header_end = self._class_header_end(node, body)
            qualified = self.add_symbol(
                node,
                name,
                scope,
                "class",
                body,
                exported=not name.startswith("_") and not scope,
                header_end=header_end,
            )
            if body is not None:
                self.visit_children(body, [*scope, name], qualified, True)
            return
        if kind == "call":
            func = node.child_by_field_name("function")
            if func is not None and func.type == "identifier":
                self.calls.append(CallInfo(caller, _text(func), False))
            elif func is not None and func.type == "attribute":
                self.calls.append(
                    CallInfo(caller, _text(func.child_by_field_name("attribute")), True)
                )
        elif kind == "import_statement":
            for child in node.named_children:
                target = (
                    child.child_by_field_name("name") if child.type == "aliased_import" else child
                )
                if target is not None and target.type == "dotted_name":
                    self.imports.append(ImportInfo(_text(target)))
            return
        elif kind == "import_from_statement":
            self._python_from_import(node)
            return
        self.visit_children(node, scope, caller, in_class)

    def _class_header_end(self, node: Node, body: Node | None) -> int:
        start = _line(node)
        limit = start + MAX_CLASS_HEADER_LINES - 1
        if body is not None:
            for child in body.named_children:
                if child.type in (
                    "function_definition",
                    "decorated_definition",
                    "class_definition",
                ):
                    return max(start, min(_line(child) - 1, limit))
        return min(_end_line(node), limit)

    def _python_from_import(self, node: Node) -> None:
        module = node.child_by_field_name("module_name")
        level = 0
        spec = ""
        if module is not None and module.type == "relative_import":
            for child in module.children:
                if child.type == "import_prefix":
                    level = _text(child).count(".")
                elif child.type == "dotted_name":
                    spec = _text(child)
        elif module is not None:
            spec = _text(module)
        names: list[str] = []
        for child in node.children_by_field_name("name"):
            target = child.child_by_field_name("name") if child.type == "aliased_import" else child
            if target is not None:
                names.append(_text(target))
        if any(c.type == "wildcard_import" for c in node.children):
            names.append("*")
        self.imports.append(ImportInfo(spec, tuple(names), level))

    # -- javascript / typescript ---------------------------------------------
    def visit_js(
        self, node: Node, scope: list[str], caller: str | None, in_class: bool, exported: bool
    ) -> None:
        kind = node.type
        if kind == "export_statement":
            source = node.child_by_field_name("source")
            if source is not None:
                self.imports.append(ImportInfo(self._string_value(source)))
            self.visit_children(node, scope, caller, in_class, exported=True)
            return
        if kind in ("function_declaration", "generator_function_declaration"):
            name = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            qualified = self.add_symbol(node, name, scope, "function", body, exported)
            if body is not None:
                self.visit_children(body, [*scope, name], qualified, False)
            return
        if kind in ("class_declaration", "abstract_class_declaration"):
            name = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            header_end = self._js_class_header_end(node, body)
            qualified = self.add_symbol(
                node, name, scope, "class", body, exported, header_end=header_end
            )
            if body is not None:
                self.visit_children(body, [*scope, name], qualified, True)
            return
        if kind == "method_definition":
            name = _text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            qualified = self.add_symbol(node, name, scope, "method", body, exported=False)
            if body is not None:
                self.visit_children(body, [*scope, name], qualified, False)
            return
        if kind == "interface_declaration":
            name = _text(node.child_by_field_name("name"))
            self.add_symbol(
                node, name, scope, "interface", node.child_by_field_name("body"), exported
            )
            return
        if kind in ("lexical_declaration", "variable_declaration"):
            self._js_declarators(node, scope, caller, in_class, exported)
            return
        if kind == "import_statement":
            self._js_import(node)
            return
        if kind == "call_expression":
            self._js_call(node, caller)
        elif kind == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor is not None and ctor.type == "identifier":
                self.calls.append(CallInfo(caller, _text(ctor), False))
        self.visit_children(node, scope, caller, in_class)

    def _js_class_header_end(self, node: Node, body: Node | None) -> int:
        start = _line(node)
        limit = start + MAX_CLASS_HEADER_LINES - 1
        if body is not None:
            for child in body.named_children:
                if child.type == "method_definition":
                    return max(start, min(_line(child) - 1, limit))
        return min(_end_line(node), limit)

    def _js_declarators(
        self, node: Node, scope: list[str], caller: str | None, in_class: bool, exported: bool
    ) -> None:
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            value = declarator.child_by_field_name("value")
            name_node = declarator.child_by_field_name("name")
            if (
                value is not None
                and name_node is not None
                and name_node.type == "identifier"
                and value.type in ("arrow_function", "function_expression", "function")
            ):
                name = _text(name_node)
                body = value.child_by_field_name("body")
                qualified = self.add_symbol(node, name, scope, "function", body, exported)
                if body is not None:
                    self.visit_children(body, [*scope, name], qualified, False)
            elif value is not None:
                self.visit(value, scope, caller, in_class)

    def _string_value(self, node: Node) -> str:
        return _text(node).strip("'\"`")

    def _js_import(self, node: Node) -> None:
        source = node.child_by_field_name("source")
        if source is None:
            return
        names: list[str] = []
        for child in node.named_children:
            if child.type != "import_clause":
                continue
            for part in child.named_children:
                if part.type == "identifier":
                    names.append("default")
                elif part.type == "named_imports":
                    for spec in part.named_children:
                        target = spec.child_by_field_name("name")
                        if target is not None:
                            names.append(_text(target))
                elif part.type == "namespace_import":
                    names.append("*")
        self.imports.append(ImportInfo(self._string_value(source), tuple(names)))

    def _js_call(self, node: Node, caller: str | None) -> None:
        func = node.child_by_field_name("function")
        if func is None:
            return
        if func.type == "identifier":
            name = _text(func)
            args = node.child_by_field_name("arguments")
            if name == "require" and args is not None and args.named_children:
                first = args.named_children[0]
                if first.type == "string":
                    self.imports.append(ImportInfo(self._string_value(first)))
                    return
            self.calls.append(CallInfo(caller, name, False))
        elif func.type == "member_expression":
            prop = func.child_by_field_name("property")
            if prop is not None:
                self.calls.append(CallInfo(caller, _text(prop), True))


def parse_file(path: str, data: bytes) -> ParsedFile | None:
    """Parse a source file; returns None for unsupported languages."""
    language = language_for(path)
    if language is None:
        return None
    tree = _parser(language).parse(data)
    walker = _Walker(data, "python" if language == "python" else "js")
    walker.visit_children(tree.root_node, [], None, False)
    text = data.decode("utf-8", errors="replace")
    parsed: Any = ParsedFile(
        path=path,
        language="python" if language == "python" else language,
        content_hash=content_hash(data),
        lines=text.splitlines(),
        symbols=walker.symbols,
        calls=walker.calls,
        imports=walker.imports,
        is_test=is_test_path(path),
    )
    return parsed
