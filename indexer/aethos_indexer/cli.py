"""Entry point: python -m aethos_indexer --api-url https://your-aethos.example"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import httpx

from aethos_indexer.chunk import file_payload
from aethos_indexer.embed import attach_embeddings, load_model
from aethos_indexer.graph import build_edges
from aethos_indexer.parse import ParsedFile, language_for, parse_file
from aethos_indexer.upload import MAX_EDGES_PER_BATCH, MAX_FILES_PER_BATCH, IndexApi, batched
from core.paths import DEFAULT_IGNORE_GLOBS, path_matches

MAX_FILE_BYTES = 300_000


SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"})


def _walk(root: Path) -> list[str]:
    found: list[str] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            found.append((Path(current) / name).relative_to(root).as_posix())
    return found


def discover(root: Path) -> list[str]:
    """Tracked files via git; falls back to walking the directory outside a git checkout."""
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "ls-files", "-z"],  # noqa: S607
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8", errors="replace")
        paths = [p for p in out.split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = _walk(root)
    return sorted(p for p in paths if language_for(p) and not path_matches(p, DEFAULT_IGNORE_GLOBS))


def parse_repo(root: Path, paths: list[str]) -> tuple[dict[str, ParsedFile], list[str]]:
    parsed: dict[str, ParsedFile] = {}
    failures: list[str] = []
    for path in paths:
        file_path = root / path
        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                continue
            result = parse_file(path, file_path.read_bytes())
        except Exception as exc:  # one bad file must not fail the whole run
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        if result is not None:
            parsed[path] = result
    return parsed, failures


def oidc_token(audience: str) -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        raise SystemExit(
            "No OIDC token available. Add `permissions: id-token: write` to the workflow job."
        )
    response = httpx.get(
        url,
        params={"audience": audience},
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return str(response.json()["value"])


def current_sha(root: Path) -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aethos-indexer")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--sha")
    parser.add_argument("--audience", help="OIDC audience (defaults to --api-url)")
    parser.add_argument("--token", help="Bearer token (testing); otherwise GitHub OIDC is used")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not upload")
    parser.add_argument("--no-embed", action="store_true", help="Skip BGE embeddings")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    parsed, failures = parse_repo(root, discover(root))
    edges = build_edges(parsed)
    print(
        f"Parsed {len(parsed)} files, {sum(len(f.symbols) for f in parsed.values())} symbols, "
        f"{len(edges)} edges; {len(failures)} file(s) skipped due to errors."
    )
    for failure in failures[:20]:
        print(f"  skipped {failure}", file=sys.stderr)
    if args.dry_run:
        return 0

    sha = args.sha or current_sha(root)
    token = args.token or oidc_token(args.audience or args.api_url)
    api = IndexApi(args.api_url, token)
    try:
        plan = api.begin(sha, [{"path": p, "hash": f.content_hash} for p, f in parsed.items()])
        changed = [p for p in plan["changed"] if p in parsed]
        print(f"{len(changed)} changed file(s) to upload, {plan['deleted']} removed.")
        payloads = [file_payload(parsed[p]) for p in changed]
        embed = None if args.no_embed or not payloads else load_model()
        if embed is not None:
            print(f"Embedded {attach_embeddings(payloads, embed)} code chunk(s).")
        for batch in batched(payloads, MAX_FILES_PER_BATCH):
            api.files(sha, batch)
        edge_payloads = [e.as_dict() for e in edges]
        if not edge_payloads:
            api.edges([], first=True)
        for number, batch in enumerate(batched(edge_payloads, MAX_EDGES_PER_BATCH)):
            api.edges(batch, first=number == 0)
        result = api.finalize(sha)
    except Exception:
        api.fail()
        raise
    print(f"Index ready: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
