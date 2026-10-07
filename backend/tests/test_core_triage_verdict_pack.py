from core.diff import parse_unified_diff
from core.lexical import identifier_tokens, similarity
from core.pack import PackItem, SymbolRef, build_pack, render_pack, symbols_overlapping
from core.paths import is_test_path, path_matches
from core.schemas import Severity
from core.triage import Risk, TriageConfig, triage
from core.verdict import (
    FindingSignal,
    Verdict,
    VerdictInputs,
    compute_verdict,
)


def _diff(path: str, added: int = 3) -> str:
    body = "\n".join(f"+line{i}" for i in range(added))
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,0 +1,{added} @@\n{body}\n"
    )


def _run(path: str, author: str = "dev", kind: str = "User", added: int = 3):
    files = parse_unified_diff(_diff(path, added))
    return triage(files, author_login=author, author_type=kind, config=TriageConfig())


def test_triage_skips_bots_lockfiles_docs():
    assert _run("src/a.py", "dependabot[bot]", "Bot").reason == "PR author is a bot"
    assert _run("package-lock.json").skip
    assert _run("pnpm-lock.yaml").skip
    assert _run("README.md").reason == "Documentation-only change"
    assert _run("dist/app.min.js").skip


def test_triage_reviews_code_and_flags_large():
    result = _run("src/a.py")
    assert not result.skip and result.risk == Risk.LOW
    big = triage(
        parse_unified_diff(_diff("src/a.py", 50)),
        author_login="dev",
        author_type="User",
        config=TriageConfig(max_changed_lines=10),
    )
    assert big.skip and "too large" in (big.reason or "")


def test_path_helpers():
    assert path_matches("src/auth/login.py", ["src/auth/**"])
    assert path_matches("a/b/c.min.js", ["**/*.min.js"])
    assert not path_matches("src/authx/login.py", ["src/auth/**"])
    assert is_test_path("tests/test_a.py") and is_test_path("web/a.test.ts")
    assert not is_test_path("src/contest.py")


def test_verdict_rules():
    blocker = FindingSignal(Severity.HIGH, 0.9, "bug", "SQL injection")
    weak = FindingSignal(Severity.HIGH, 0.4, "bug", "Maybe a bug")
    nit = FindingSignal(Severity.NIT, 0.9, "style", "Naming")

    assert compute_verdict(VerdictInputs(findings=(blocker,))).verdict == Verdict.NOT_READY
    assert compute_verdict(VerdictInputs(is_draft=True)).verdict == Verdict.NOT_READY
    assert compute_verdict(VerdictInputs(mergeable=False)).verdict == Verdict.NOT_READY
    assert compute_verdict(VerdictInputs(ci_state="failure")).verdict == Verdict.NOT_READY
    assert (
        compute_verdict(VerdictInputs(findings=(weak,))).verdict == Verdict.READY_WITH_SUGGESTIONS
    )
    assert (
        compute_verdict(VerdictInputs(findings=(nit,), tests_changed=True)).verdict == Verdict.READY
    )
    assert compute_verdict(VerdictInputs()).verdict == Verdict.READY
    assert (
        compute_verdict(VerdictInputs(source_lines_changed=50)).verdict
        == Verdict.READY_WITH_SUGGESTIONS
    )
    assert compute_verdict(VerdictInputs(high_fan_in=("save",))).verdict == (
        Verdict.READY_WITH_SUGGESTIONS
    )
    assert compute_verdict(VerdictInputs(llm_ok=False)).verdict == Verdict.INCONCLUSIVE
    assert compute_verdict(VerdictInputs(coverage_complete=False)).verdict == Verdict.INCONCLUSIVE
    # A blocker still wins over partial coverage.
    assert (
        compute_verdict(VerdictInputs(findings=(blocker,), coverage_complete=False)).verdict
        == Verdict.NOT_READY
    )


def test_pack_respects_budget_and_priority():
    big = "x" * 4000  # 1000 tokens
    candidates = [
        PackItem("meta", "PR", "title", "pr", order=0),
        PackItem("diff", "a.py hunk 1", big, "changed", score=1.0, order=1),
        PackItem("diff", "b.py hunk 1", big, "changed", score=0.5, order=2),
        PackItem("symbols", "func", "y" * 400, "enclosing", score=1.0, order=3),
        PackItem("map", "map", "z" * 400, "map", order=4),
    ]
    pack = build_pack(candidates, budget=1300)
    titles = [i.title for i in pack.items]
    assert pack.tokens_used <= 1300 + 2  # meta is mandatory and tiny
    assert "a.py hunk 1" in titles and "b.py hunk 1" not in titles
    assert not pack.diff_complete
    assert any(d.title == "b.py hunk 1" for d in pack.dropped)
    assert titles[0] == "PR"  # priority order


def test_pack_rollover_uses_leftover_budget():
    candidates = [
        PackItem("meta", "PR", "t", "pr"),
        PackItem("diff", "d", "d" * 40, "changed"),
        PackItem("tests", "t1", "t" * 4000, "test", order=1),  # 1000 tokens, over its 5% share
    ]
    pack = build_pack(candidates, budget=2000)
    assert "t1" in [i.title for i in pack.items]
    assert pack.diff_complete
    assert "Related tests" in render_pack(pack)


def test_pack_is_deterministic():
    items = [PackItem("similar", f"s{i}", "q" * 40, "sim", score=0.5, order=i) for i in range(6)]
    a = build_pack(list(items), 100)
    b = build_pack(list(reversed(items)), 100)
    assert [i.title for i in a.items] == [i.title for i in b.items]


def test_symbols_overlapping():
    symbols = [
        SymbolRef("a", "a", "function", 1, 10),
        SymbolRef("b", "B.b", "method", 12, 20),
        SymbolRef("c", "c", "function", 30, 40),
    ]
    hit = symbols_overlapping([(9, 13)], symbols)
    assert [s.name for s in hit] == ["a", "b"]
    assert symbols_overlapping([(50, 60)], symbols) == []


def test_lexical_tokens_and_similarity():
    tokens = identifier_tokens("def getUserProfile(user_id): return fetch_profile_data(user_id)")
    assert {"user", "profile", "fetch", "data"} <= tokens
    assert "def" not in tokens
    assert similarity(tokens, tokens) == 1.0
    assert similarity(tokens, {"unrelated", "words"}) == 0.0
