from apps.indexing.code.chunk import file_payload
from apps.indexing.code.graph import build_edges
from apps.indexing.code.parse import parse_file

PY_UTILS = b'''\
import os


def helper(x):
    """Doubles x."""
    return x * 2


class Service:
    """Does things."""

    limit = 3

    def run(self, value):
        return helper(value)

    def _private(self):
        return os.getcwd()
'''

PY_APP = b"""\
from app.utils import helper, Service


def main():
    s = Service()
    return helper(2) + s.run(1)
"""

PY_TEST = b"""\
from app.main import main


def test_main():
    assert main() == 5
"""

TS_LIB = b"""\
export function add(a: number, b: number): number {
  return a + b;
}

export const double = (n: number) => add(n, n);

export class Calc {
  total(a: number) {
    return add(a, a);
  }
}

export interface Options { verbose: boolean }
"""

TS_USE = b"""\
import { add, double } from "./lib";

export function run() {
  return add(1, 2) + double(3);
}
"""


def _symbols(parsed):
    return {s.qualified_name: s for s in parsed.symbols}


def test_python_symbols_and_calls():
    parsed = parse_file("app/utils.py", PY_UTILS)
    symbols = _symbols(parsed)
    assert set(symbols) == {"helper", "Service", "Service.run", "Service._private"}
    assert symbols["helper"].kind == "function" and symbols["helper"].exported
    assert symbols["Service.run"].kind == "method"
    assert not symbols["Service._private"].exported
    assert symbols["helper"].signature == "def helper(x)"
    assert symbols["helper"].start_line == 4 and symbols["helper"].end_line == 6
    assert ("Service.run", "helper", False) in {(c.caller, c.name, c.is_attr) for c in parsed.calls}
    assert [i.spec for i in parsed.imports] == ["os"]


def test_python_class_chunk_is_header_only():
    parsed = parse_file("app/utils.py", PY_UTILS)
    payload = file_payload(parsed)
    names = [s["qualified_name"] for s in payload["symbols"]]
    class_index = names.index("Service")
    class_chunk = next(c for c in payload["chunks"] if c["symbol_index"] == class_index)
    assert "limit = 3" in class_chunk["text"]
    assert "def run" not in class_chunk["text"]
    run_chunk = next(
        c for c in payload["chunks"] if c["symbol_index"] == names.index("Service.run")
    )
    assert "helper(value)" in run_chunk["text"]
    assert " helper " in run_chunk["search_tokens"]


def test_typescript_symbols_and_imports():
    lib = parse_file("src/lib.ts", TS_LIB)
    assert set(_symbols(lib)) == {"add", "double", "Calc", "Calc.total", "Options"}
    assert _symbols(lib)["add"].exported and _symbols(lib)["double"].kind == "function"
    use = parse_file("src/use.ts", TS_USE)
    assert [(i.spec, i.names) for i in use.imports] == [("./lib", ("add", "double"))]


def test_graph_edges_python_and_typescript():
    files = {
        p: parse_file(p, data)
        for p, data in {
            "app/utils.py": PY_UTILS,
            "app/main.py": PY_APP,
            "tests/test_main.py": PY_TEST,
            "src/lib.ts": TS_LIB,
            "src/use.ts": TS_USE,
        }.items()
    }
    edges = {
        (e.kind, e.from_path, e.from_symbol, e.to_path, e.to_symbol): e for e in build_edges(files)
    }
    assert ("imports", "app/main.py", None, "app/utils.py", None) in edges
    assert ("imports", "src/use.ts", None, "src/lib.ts", None) in edges
    assert ("tests", "tests/test_main.py", None, "app/main.py", None) in edges
    assert ("calls", "app/main.py", "main", "app/utils.py", "helper") in edges
    assert edges[("calls", "app/main.py", "main", "app/utils.py", "helper")].confidence == 0.9
    assert ("calls", "app/utils.py", "Service.run", "app/utils.py", "helper") in edges
    assert ("calls", "src/use.ts", "run", "src/lib.ts", "add") in edges
    assert ("calls", "src/lib.ts", "Calc.total", "src/lib.ts", "add") in edges
    # attribute call `s.run(1)` resolves only with low confidence, never above 0.6
    low = [e for e in edges.values() if e.to_symbol == "Service.run"]
    assert all(e.confidence <= 0.6 for e in low)


def test_parse_is_deterministic_and_skips_unsupported():
    assert parse_file("README.md", b"# hi") is None
    a = parse_file("app/utils.py", PY_UTILS)
    b = parse_file("app/utils.py", PY_UTILS)
    assert a.content_hash == b.content_hash and a.symbols == b.symbols
