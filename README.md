<div align="center">

<img src="frontend/public/aethos-icon.svg" alt="Aethos" width="96" height="96" />

# Aethos

**Know if a pull request is ready to merge.**

Mention `@aethos-agent` on a PR. Get a verdict, inline suggestions, and the bottlenecks worth fixing first.

[Live app](https://aethos-mu.vercel.app) · [Setup](SETUP.md) · [Architecture](docs/ARCHITECTURE.md) · [Plan](PLAN.md)

![Python](https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/django-5-092e20?logo=django&logoColor=white)
![React](https://img.shields.io/badge/react-19-61dafb?logo=react&logoColor=black)
![Tests](https://img.shields.io/badge/tests-pytest%20%2B%20vitest-brightgreen)

</div>

---

## Why

Most AI reviewers read the whole repository or just the diff. Aethos indexes your codebase once, then gives the model only what matters: the changed code, its callers and callees, similar existing code and the related tests. Reviews stay fast and cheap, and the verdict is computed in code, so it is explainable.

## Features

- **Merge-readiness verdict**: `ready`, `ready with suggestions` or `not ready`, with every reason listed.
- **Inline suggestions** you can apply in one click, plus the performance bottlenecks to fix first.
- **Code index** of symbols, calls, imports and tests (tree-sitter for Python, JavaScript and TypeScript), refreshed on every push.
- **Semantic search** over your code with NVIDIA `nemotron-3-embed-1b`, falling back to keyword matching.
- **Dashboard** with stats, repositories (most recently reviewed first), reviews and a context-pack inspector.
- **Comment-only**: never approves, merges or edits your code.

## How it works

```
@aethos ─▶ webhook ─▶ QStash ─▶ triage ─▶ pack ─▶ review ─▶ post
                                 skip      index    one NIM    one GitHub
                                 bots,     lookup   JSON       review with
                                 docs      (no LLM) call       inline comments
```

1. **Triage** skips bot PRs, lockfile-only, docs-only and oversized changes at zero LLM cost.
2. **Pack** builds a token-budgeted context from the index. No LLM is involved, and the pack is stored so you can inspect it.
3. **Review** makes a single `nvidia/nemotron-3-super-120b-a12b` call that returns structured findings.
4. **Post** computes the verdict from the findings plus CI status, conflicts, draft state and test changes, then posts one GitHub review.

Indexing runs on the server: it downloads the default branch, parses it, and embeds the chunks in short queue steps. It starts when you install the app, on every push to the default branch, and from the **Re-index** button.

## Stack

| | |
|---|---|
| API | Django + django-ninja on Vercel |
| Database | Neon Postgres with pgvector |
| Queue | Upstash QStash |
| Models | NVIDIA NIM: `nemotron-3-super-120b-a12b` (reviews), `nemotron-3-embed-1b` (embeddings) |
| Frontend | Vite, React, TypeScript, Tailwind v4, shadcn/ui on Base UI |

## Quick start

```bash
git clone https://github.com/heysagnik/aethos && cd aethos
cp .env.example .env              # fill in your keys, see SETUP.md
uv sync && cd frontend && pnpm install && cd ..

make dev-backend                  # Django on :8000
make dev-frontend                 # Vite on :5173
```

Open http://localhost:5173 and sign in with GitHub. [SETUP.md](SETUP.md) lists every account, key and GitHub App setting you need.

## Development

```bash
make check                        # lint, types, tests, migrations, frontend checks
uv run python backend/manage.py compare --repo owner/name --pr 12   # Aethos vs. baseline
uv run python backend/manage.py show_review 42                      # inspect a review
```

No `make` (Windows)? Run the same checks directly:

```bash
uv run ruff check . && uv run ruff format --check .
DJANGO_SETTINGS_MODULE=aethos.settings.test MYPYPATH=backend PYTHONPATH=backend uv run mypy backend/core backend/apps
DJANGO_SETTINGS_MODULE=aethos.settings.test uv run pytest
cd frontend && pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

## Project layout

```
backend/core/       pure Python: diff parsing, triage, verdict, packing, prompts
backend/apps/       Django apps: accounts, github, repos, indexing, reviews, dashboard
frontend/           React dashboard and landing page
api/index.py        Vercel entry point
docs/               architecture and design notes
```

## Status

Phase 1 (install flow, reviews, index, context packs, verdict, dashboard, baseline comparison) is built and tested, and the app is deployed. The NVIDIA calls and server-side indexing have only been tested against mocks so far; [SETUP.md](SETUP.md) lists what to check on the first real run. Threads, memory, feedback learning and delta re-review are planned in [PLAN.md](PLAN.md).

Contributing with an AI agent? Read [AGENT.md](AGENT.md) first.
