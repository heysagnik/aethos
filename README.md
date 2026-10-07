# Aethos

A GitHub App that reviews pull requests when you mention it. Comment `@aethos` on a PR and it replies with a **merge-readiness verdict**, inline **suggestions**, and the **bottlenecks** worth fixing first. It reads an index of your codebase instead of the whole repository, so reviews stay fast and cheap.

- Landing page with an **Install on GitHub** button, then a minimal dashboard built with [Kumo](https://kumo-ui.com): stats, repositories, reviews, and a context-pack inspector.
- Django (django-ninja) API on Vercel, Neon Postgres (+ pgvector), QStash for step delivery, Groq for the LLM, BAAI bge embeddings computed in the GitHub Action indexer.
- Never approves, merges or edits code. Reviews are comment-only.

**Start here:** [SETUP.md](SETUP.md) lists every account, key and setting you need.
Design and phase plan: [PLAN.md](PLAN.md). Rules for coding agents working on this repo: [AGENT.md](AGENT.md). Frontend design notes: [docs/DESIGN.md](docs/DESIGN.md).

## How a review works

```
@aethos comment ─▶ webhook (verify, dedupe) ─▶ QStash ─▶ triage ─▶ pack ─▶ review ─▶ post
                                                         skip       index    Groq     one GitHub
                                                         bots,      lookup   JSON     review with
                                                         locks,     (no LLM) output   inline comments
                                                         docs
```

1. **Triage** skips bot PRs, lockfile-only, docs-only and oversized changes at zero LLM cost.
2. **Pack** builds a token-budgeted context: the diff, the enclosing code, callers and callees from the dependency graph, similar existing code (nearest neighbours of the changed code by stored bge embedding, or keyword matching when there are none), related tests and a repository map. No LLM is involved; the pack is stored so you can inspect it.
3. **Review** makes one Groq call that returns structured JSON (findings with severity and confidence).
4. **Post** computes the verdict *in code* from the findings plus CI status, merge conflicts, draft state, test changes and how many other symbols depend on the changed code, then posts a single GitHub review.

The index is built by a GitHub Action (`action/`) using tree-sitter (Python, JavaScript, TypeScript) and uploaded with the Action's OIDC token. Only files whose content hash changed are re-uploaded.

## Repository layout

```
backend/core/       pure Python: diff parsing, triage, verdict, pack building, prompts, rendering
backend/apps/       Django apps: accounts, github, repos, indexing, reviews, dashboard
indexer/            tree-sitter indexer used by the GitHub Action
action/             composite GitHub Action
frontend/           Vite + React + Kumo dashboard and landing page
api/index.py        Vercel entry point
```

## Commands

```bash
make check          # everything CI runs
make dev-backend    # Django on :8000
make dev-frontend   # Vite on :5173
uv run python backend/manage.py compare --repo owner/name --pr 12   # Aethos vs baseline
uv run python backend/manage.py show_review 42                      # inspect a review
```

Without `make` (for example on Windows), run the same checks directly:

```bash
uv run ruff check . && uv run ruff format --check .
DJANGO_SETTINGS_MODULE=aethos.settings.test MYPYPATH=backend:indexer PYTHONPATH=backend uv run mypy backend/core backend/apps indexer/aethos_indexer
DJANGO_SETTINGS_MODULE=aethos.settings.test uv run pytest
cd frontend && pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

## Status

Phase 1 (install flow, `@aethos` reviews, index, context packs, verdict, dashboard, baseline comparison) is implemented and covered by tests (Python: pytest, ruff, mypy; frontend: vitest, tsc, eslint). It has not been run against live GitHub, Groq, Neon, Vercel or QStash yet; see section 6 of [SETUP.md](SETUP.md). Phase 2 (threads, memory, feedback learning, verifier, delta re-review, evaluation) is planned in [PLAN.md](PLAN.md).
