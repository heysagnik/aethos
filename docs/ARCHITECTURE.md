# Aethos architecture

How the app works end to end.

```
                              ┌──────────────────────────────┐
                              │  GitHub                      │
                              │  - repo + PRs                │
                              │  - Aethos GitHub App         │
                              │  - Actions runner (indexer)  │
                              └──┬───────────┬────────────┬──┘
        PR comment "@aethos"     │           │            │  push to main
        + install events         │ webhook   │ OAuth      │  (workflow)
                                 ▼           │            ▼
┌──────────────────────── Vercel ────────────┼──────────────────────────┐
│                                            │                          │
│  React SPA (Kumo UI)  ◄── JSON API ──►  Django (django-ninja)         │
│  landing, dashboard,                     /api/github/*   webhook,     │
│  repo settings,                                          install,     │
│  review + pack inspector                                 setup        │
│                                          /api/auth/*     login        │
│                                          /api/dashboard/* stats       │
│                                          /api/index/*    ingest       │
│                                          /api/steps/*    pipeline     │
└───────────────────────┬───────────────────────────┬───────────────────┘
                        │ SQL                       │ publish step
                        ▼                           ▼
          ┌───────────────────────────┐   ┌────────────────────┐
          │ Neon Postgres + pgvector  │   │ Upstash QStash     │
          │ users, installs, repos    │   │ delivers each step │
          │ files, symbols, edges,    │   │ as a short HTTPS   │
          │ chunks (+768-d vectors)   │   │ call, with retries │
          │ reviews, findings, usage  │   └────────────────────┘
          └───────────────────────────┘
                                          Groq (LLM) ◄── review step
```

## Flow 1: install

1. The user clicks **Install** on the landing page. The SPA goes to `/api/github/install`, then to GitHub.
2. The user picks a repo. GitHub sends an `installation` webhook, and the user's browser is redirected to `/api/github/setup`.
3. Django verifies the state nonce, logs the user in through GitHub OAuth, and stores `Installation`, `Repository` and `InstallationMember`.
4. The user lands on the dashboard.

## Flow 2: build the index (once, then on every push)

1. The GitHub Action runs `aethos_indexer` on the runner.
2. The indexer parses the repo with tree-sitter (Python, JS, TS) into symbols, import/call/test edges and chunks.
3. It authenticates with a GitHub OIDC token, which the server checks for the repo and the default branch.
4. `/begin` compares file hashes, so only changed files go on.
5. The runner embeds those chunks with BGE (`BAAI/bge-base-en-v1.5` via `fastembed`), then sends `/files` with chunks and vectors, `/edges`, and `/finalize`.
6. Neon now holds the code graph and the vectors.

## Flow 3: review a PR

1. Someone comments `@aethos` on a PR. GitHub sends an `issue_comment` webhook.
2. Django checks the HMAC signature, dedupes by delivery ID, parses the command and creates a `Review` row. It then enqueues the first step in QStash.
3. QStash calls each step in turn. Each step is short, reads and writes the DB, and is safe to retry.

| Step | What it does |
|---|---|
| **triage** | Fetches PR metadata and the diff from GitHub, applies ignore rules, decides the risk and which files to review. |
| **pack** | Builds the context pack from the DB with no LLM: the diff, the enclosing symbols, callers and callees, tests, similar code and a repo map. The pack is token-budgeted and saved on the review. |
| **review** | Sends the pack to Groq in JSON mode and validates the findings against the diff lines. |
| **post** | Computes the verdict in code and posts one COMMENT review with inline comments and a summary. |

4. The verdict is ready, ready with suggestions, not ready or inconclusive. It is computed in code from the findings, CI state, draft status, mergeability, test coverage and fan-in, not by the LLM.

### How "similar code" works in the pack step

```
changed symbols (base branch)
   └─► their stored 768-d vectors ──► pgvector <=> (HNSW) ──► nearest chunks in other files
                                       └─ none stored? ──► identifier-token matching
```

Limits: the query is the base-branch version of the changed code, and brand-new files have no stored vectors, so they use keyword matching.

## Flow 4: dashboard

The SPA reads `/api/dashboard/*` (overview stats, repos, review list, review detail) with a cookie session and a CSRF header. Repo settings are saved by `PATCH`. The review page shows findings, the pack inspector (what was sent to the model and what was dropped) and token and cost usage.

## What runs where

- **Vercel:** static SPA and short Django functions only. Nothing slow runs there.
- **GitHub Actions:** parsing and embedding, the heavy work.
- **QStash:** splits a review into short retryable calls, so no single function runs long.
- **Neon:** all state, including the vectors.
- **Groq:** the only paid-per-token call, once per review (twice if the first answer is invalid).
