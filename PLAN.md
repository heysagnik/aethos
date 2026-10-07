# Aethos: Plan

A GitHub App that lives in your repo. Mention `@aethos` on a pull request and it tells you whether the PR is ready to merge, with suggestions and bottlenecks. It does this without reading the whole codebase, using a pre-built code index and memory. A web dashboard shows stats and (Phase 2) lets you talk to the codebase in threads.

This file supersedes `PROJECT_PLAN.md` and `PHASE1_ENGINEERING_PLAN.md`, which assumed Node and a different dashboard.

Items marked **[verify]** depend on vendor limits or APIs that change. Check them against current docs before relying on them.

---


## Implementation notes (what was built, and where it differs from the plan below)

Phase 1 is implemented. The text below is the original plan. Where it mentions Kumo, Groq, bge, the GitHub Action or OIDC, the table and notes here describe what is actually built.

| Plan said | What was built | Why |
|---|---|---|
| Anthropic API | **NVIDIA NIM chat completions** (`nvidia/nemotron-3-super-120b-a12b`, JSON mode, OpenAI-compatible API, shared `NVIDIA_API_KEY`) | Requested (first Groq, then NIM). Prices (`LLM_PRICES`) are empty, so costs show $0 until you add them; JSON-mode support on NIM must be checked against NVIDIA's docs. |
| pgvector embeddings for "similar code" | **NVIDIA NIM `nvidia/nemotron-3-embed-1b`** (2048-d) computed by the server while indexing, stored in a pgvector `halfvec(2048)` column with an HNSW index; reviews query with the stored vectors of the changed symbols; identifier-token matching is the fallback | `halfvec` keeps the HNSW index possible above 2000 dimensions. No model runs on Vercel. |
| Index built on install | **Index built by the server** in queued steps (`index`, then `embed`): on install or repository add, on every push to the default branch, and from the dashboard's Re-index button | The repository is downloaded as a tarball with the installation token and parsed with tree-sitter; no workflow file is added to user repositories. Requires the Contents (read) permission and the Push event. |
| Prompt caching | Not used | The prompt is ordered stable-first so provider-side caching can help if it is available. |
| Charts | A small token-based bar series | A charting library would add ECharts-sized weight; skipped to keep the bundle small. |
| Index updates only re-send changed files | Each index run parses the whole repository, replaces symbols and chunks **only for files whose hash changed**, and rebuilds all edges | Edges between unchanged and changed files must be re-resolved. |
| Enclosing symbol bodies from the PR head | Bodies come from the **indexed base branch**; hunks are mapped by their old-side line numbers | Avoids fetching every changed file. The review footer notes when the index is older than the PR base. |
| Check run publishing | Not built | Optional in the plan; needs the Checks write permission. |
| Review modes | `aethos` and `baseline` stored per review; `manage.py compare` runs both as dry runs | Powers the savings figure on the Overview page. |

Later changes: the dashboard moved from Kumo to shadcn/ui on Base UI; the GitHub Action indexer, its OIDC login and `/api/index` upload API were removed; repositories are listed most recently reviewed first; and the Aethos mascot (an olive with round glasses) is the logo and favicon.

Added beyond the plan: `.aethos.yml` per-repository overrides, `manage.py show_review` (pack inspector on the command line), a CSRF-protected session API, OpenAPI-generated frontend types, and CI.

Not yet verified against live services: see section 6 of [SETUP.md](SETUP.md).

---

## 1. Product surface

| Surface | What the user sees |
|---|---|
| **Landing page** (`/`) | One-page site with an **Install Aethos** button. The button opens GitHub's install screen, where the user picks the repos to install on. |
| **Dashboard** (`/app`) | Clean, minimal UI built on Kumo. Phase 1: repos, stats, reviews, review detail. Phase 2: **threads** to chat about the codebase. |
| **GitHub PR** | A user comments `@aethos` (optionally with instructions). Aethos replies with a **merge-readiness verdict**, inline **suggestions**, and **bottlenecks**. It never approves or merges. |

### 1.1 Install flow
1. Landing page: **Install** -> `https://github.com/apps/<APP_SLUG>/installations/new`.
2. GitHub shows the repo picker (all repos or selected repos). The user installs.
3. GitHub redirects to our **Setup URL** (`/api/github/setup?installation_id=...&setup_action=install&code=...`). "Request user authorization (OAuth) during installation" is enabled on the App, so the redirect carries an OAuth `code`.
4. Backend exchanges the code, identifies the GitHub user, confirms the user can access that installation, creates a Django session, links user to installation, and redirects to `/app`.
5. The `installation` webhook (and the setup callback, whichever arrives first) creates the `Installation` and `Repository` rows and queues the first **index build**.
6. The dashboard shows each repo's index progress.

### 1.2 PR interaction
- Trigger: a PR comment containing `@<APP_SLUG>`. Text after the mention is treated as instructions (`@aethos focus on security`).
- Aethos reacts with 👀 immediately, then posts one batched review (comment-only, never approve/request-changes) and a summary comment.
- Summary contains: **verdict**, why, blocking issues, suggestions, bottlenecks, and a footer with tokens and cost.
- Optionally (if Checks permission is granted) it publishes an `Aethos` check run with the verdict. Phase 1 may skip this.
- No auto-review on PR open in Phase 1. On-demand only keeps cost near zero. An `auto_review: true` repo setting is a Phase 2 option.

### 1.3 Merge-readiness verdict
The verdict is computed **by code** from structured inputs, not decided freely by the LLM. This makes it explainable and testable.

| Input | Source |
|---|---|
| Findings with severity, confidence, category | LLM, structured output |
| Mergeability and conflicts | GitHub API (`mergeable`, `mergeable_state`) |
| CI status | GitHub API (check runs / combined status) |
| Draft state | GitHub API |
| Tests changed for non-trivial source changes | Diff heuristic using the index (test edges) |
| High fan-in symbols changed | Graph (index) |

| Verdict | Rule (configurable) |
|---|---|
| `not_ready` | Any finding with severity `critical`/`high` and confidence >= 0.7; or conflicts; or failing required CI; or PR is draft |
| `ready_with_suggestions` | No blockers, but medium findings, missing tests, or high-fan-in changes |
| `ready` | No findings above `low`, CI green, no conflicts |
| `inconclusive` | PR too large, index not ready, or LLM output failed validation |

**Bottlenecks** are two things, labelled separately in the output:
1. **Performance/complexity hotspots in the changed code** (LLM category `performance`): N+1 queries, O(n^2) loops, blocking calls in async code, unbounded queries, missing indexes for new queries.
2. **Blast radius**: changed symbols with high fan-in from the dependency graph (computed without the LLM).

---

## 2. Architecture

```
Browser ──> Vercel (static React SPA: landing + dashboard)
              │  /api/*  (same origin, so cookies work and there is no CORS)
              v
        Django (django-ninja API) on Vercel Python functions
          ├─ /api/github/webhook      verify HMAC, dedupe, enqueue
          ├─ /api/github/setup        post-install callback (OAuth code)
          ├─ /api/auth/*              GitHub OAuth session
          ├─ /api/steps/<step>        QStash targets (triage, pack, review, post)
          ├─ /api/index/ingest        called by the GitHub Action (OIDC)
          └─ /api/dashboard/*         stats, repos, reviews (session auth)
              │
              ├─ Neon Postgres + pgvector (all state)
              ├─ Upstash QStash (async step delivery, retries)
              └─ Anthropic API (review model + cheap model)

GitHub Actions (in the installed repo, on push to default branch)
   tree-sitter parse of changed files -> symbols, edges, chunks, embeddings
   -> POST /api/index/ingest with a GitHub OIDC token
```

Principles:
1. **No long work on Vercel.** Every function is one short step. Parsing and embedding run in GitHub Actions.
2. **State lives in Neon.** Any step can be retried alone.
3. **Idempotent everywhere.** Webhook redelivery or QStash retry never produces a second review.
4. **Retrieval is deterministic code.** The LLM sees a bounded, inspectable context pack.
5. **Every LLM call is metered** (tokens, cost, latency) and every pack is stored so it can be replayed.

### 2.1 Technology

| Concern | Choice |
|---|---|
| Backend | Python 3.12, Django 5.x, **django-ninja** (Pydantic schemas, OpenAPI) |
| Database | Neon Postgres (pooled endpoint), psycopg 3, pgvector (`Chunk.embedding`, HNSW cosine index) |
| Queue | Upstash QStash (`qstash` Python SDK) |
| LLM | Groq Python SDK (JSON mode); Pydantic models validate the output |
| GitHub | `githubkit` (or PyGithub) + PyJWT for App auth |
| Indexer | Python `tree-sitter` + grammars, run in GitHub Actions |
| Frontend | Vite + React + TypeScript (strict), **@cloudflare/kumo** (Kumo), Tailwind CSS, `@phosphor-icons/react`, React Router, TanStack Query |
| API types | `openapi-typescript` generated from Django Ninja's OpenAPI schema |
| Tooling | uv, ruff, mypy (+ django-stubs), pytest + pytest-django, pnpm, ESLint, Prettier, Vitest + Testing Library, pre-commit |
| Hosting | Vercel (static frontend + Python functions) |

Notes:
- Kumo is a React component library, so the frontend is a React SPA, not Django templates. Django serves JSON only.
- Kumo is installed per its docs: `@cloudflare/kumo` with peer deps React, React DOM and `@phosphor-icons/react`; Tailwind v4 imports `@cloudflare/kumo/styles/tailwind` before `tailwindcss`, plus an `@source` for Kumo's dist files; the app root uses `isolation: isolate`. **[verify against current docs; check Kumo's license and version when installing]**
- Django on Vercel's Python runtime has limits (bundle size, cold start, no background workers) **[verify]**. The Week 1 spike (A-03) deploys a minimal Django + pgvector + QStash callback before anything else is built. If the spike fails, fall back to FastAPI-style minimal handlers on Vercel, or host Django elsewhere, and record an ADR.

### 2.2 Repository layout

```
aethos/
  PLAN.md  AGENT.md  README.md  Makefile  vercel.json  pyproject.toml
  backend/
    manage.py
    aethos/                    # Django project (settings split: base/dev/prod)
    apps/
      accounts/                # GitHub OAuth, sessions, user<->installation links
      github/                  # webhook view, setup view, App auth client, posting
      repos/                   # Installation, Repository models + sync
      indexing/                # models (File, Symbol, Edge, Chunk), ingest API
      reviews/                 # Review, Finding, UsageLog; step views; verdict engine
      dashboard/               # read-only stats/list endpoints
      threads/                 # (Phase 2) Thread, Message, chat service
      memory/                  # (Phase 2) Memory, Feedback
    core/                      # pure Python, NO Django imports, unit-tested in isolation
      diff/  triage/  pack/  verdict/  prompts/  tokens/
    tests/
  indexer/                     # Python package run by the GitHub Action
    aethos_indexer/ (parsers, graph, chunk, embed, upload)
  action/                      # action.yml (composite GitHub Action)
  frontend/
    src/
      app/ (router, providers)  pages/ (landing, dashboard, repo, review, thread)
      components/ (thin wrappers around Kumo only when needed)
      lib/ (api client, generated types)  styles/
  docs/ (ADRs, DESIGN.md, API.md)
  eval/ (fixtures and replay script)
```

Layering inside each Django app: `views/api.py` (thin) -> `services.py` (business logic, transactions) -> `selectors.py` (read queries) -> `models.py`. `core/` has the pure logic and never imports Django or touches I/O.

---

## 3. Data model (Django models, Phase 1 unless noted)

| Model | Key fields |
|---|---|
| `User` (custom) | `github_user_id` (unique), `login`, `avatar_url` |
| `Installation` | `github_installation_id` (unique), `account_login`, `account_type`, `suspended_at` |
| `InstallationMember` | `user` -> `installation`, `verified_at` (who may see it) |
| `Repository` | `installation`, `github_repo_id` (unique), `full_name`, `default_branch`, `indexed_sha`, `index_status`, `settings` (JSON: budget, thresholds, ignore paths) |
| `WebhookEvent` | `delivery_id` (PK, dedupe), `event`, `action`, `received_at`, `processed_at` |
| `IndexedFile` | `repository`, `path`, `language`, `content_hash`, `summary`, `loc`; unique (`repository`, `path`) |
| `Symbol` | `file`, `name`, `qualified_name`, `kind`, `start_line`, `end_line`, `signature`, `exported` |
| `Edge` | `repository`, `from_file/symbol`, `to_file/symbol`, `kind` (imports/calls/tests), `confidence` |
| `Chunk` | `symbol`, `file`, `part`, `text`, `token_count`, `search_tokens` |
| `Review` | `repository`, `pr_number`, `head_sha`, `base_sha`, `trigger_comment_id`, `instructions`, `mode` (aethos/baseline), `status`, `verdict`, `verdict_reasons` (JSON), `risk`, `skip_reason`, `pack` (JSON), `raw_output` (JSON), `github_review_id`, token/cost/latency fields; unique (`repository`, `pr_number`, `head_sha`, `trigger_comment_id`, `mode`) |
| `Finding` | `review`, `path`, `line`, `start_line`, `severity`, `confidence`, `category`, `title`, `body`, `suggestion`, `posted`, `github_comment_id` |
| `UsageLog` | `review`, `step`, `model`, `tokens_in/out/cached`, `cost_usd`, `duration_ms` |
| `Thread` *(P2)* | `repository`, `user`, `title`, `created_at` |
| `Message` *(P2)* | `thread`, `role`, `content`, `citations` (JSON: path, lines, symbol), usage fields |
| `Memory` *(P2)* | `repository`, `type`, `scope_path`, `text`, `embedding`, `score`, `last_used_at` |
| `Feedback` *(P2)* | `finding`, `kind` (reaction/resolved/dismissed/reply), `value` |

The embedding dimension is a single constant (`EMBEDDING_DIM`), decided in Week 1. Changing it later needs a re-embed migration.

---

## 4. Key components (design)

### 4.1 Webhook (`/api/github/webhook`)
1. `csrf_exempt`; read `request.body` (raw bytes). Verify `X-Hub-Signature-256` with `hmac.compare_digest`. Return 401 on mismatch.
2. Insert `WebhookEvent` by `X-GitHub-Delivery`; if it already exists return 200 and do nothing.
3. Route:
   - `installation`, `installation_repositories`: sync installation and repos; queue index build.
   - `issue_comment` (created, on a PR, body mentions `@<slug>`, author is not a bot): queue `triage`.
   - `push` to default branch: record target SHA (the Action does the indexing).
4. Enqueue to QStash (`retries=3`, dedup id = delivery id) and return 202 in under a second.

### 4.2 Step pipeline (`/api/steps/<step>`)
Each step verifies the QStash signature, loads the `Review`, does one thing, saves, and publishes the next step.

| Step | Work |
|---|---|
| `triage` | Create `Review` (unique key = idempotency). Fetch PR + files. Skip: bot-authored, lockfile/generated/docs-only, empty diff. Too large -> `inconclusive` with a hint to narrow the scope. Index not ready -> warn and degrade to diff-only. |
| `pack` | Fetch diff; run Context Pack Builder (or baseline builder); save `pack`. |
| `review` | One LLM call with structured output; filter by confidence; cap count; record usage. |
| `post` | Re-check head SHA (if changed, mark `superseded`, post nothing). Compute verdict from findings + signals. Validate lines against the diff; post one batched review + summary; update reaction. |

### 4.3 Diff handling (`core/diff`)
Parse unified diffs into hunks and build a **commentable-lines map** (new-side lines present in the diff). GitHub returns 422 for comments outside the diff, so every finding is validated; invalid ones move into the summary. Handle renames, deletions, binaries, truncated patches. This is pure code and is the most heavily tested module.

### 4.4 Indexer (GitHub Action + `indexer/`)
- Trigger: `push` to default branch, plus `workflow_dispatch` for a full rebuild. The Action authenticates with its **OIDC token** (`permissions: id-token: write`); the server verifies it against GitHub's JWKS and checks the `repository` claim against installed repos. No DB credentials ever sit in user repos.
- Changed files: `git diff --name-status <indexed_sha> HEAD`; if `indexed_sha` is unknown, do a full index.
- Per file: `sha256(content)`; ask the server which hashes it already has and skip unchanged files.
- Parse with tree-sitter (TS/JS and Python first):
  - **Symbols**: functions, methods, classes, interfaces, exported constants, with line ranges and signatures.
  - **Import edges** (file-level), resolving relative paths and tsconfig `paths` / Python module paths. External packages ignored.
  - **Call edges** (symbol-level) resolved by name against same-file symbols and symbols from imported files. Approximate (no type checker), so each edge stores a `confidence`.
  - **Test edges**: a test file importing a source file.
- Chunk per symbol (split over ~300 lines); embed only chunks with a new `content_hash`.
- Upload in batches (body size limits **[verify]**). Update `indexed_sha` only after the last batch succeeds. When a file's exported symbols change, re-resolve edges of files that import it, in the same transaction.
- Targets: full index of a 50k-LOC repo in about 10 minutes; incremental index of a typical push under 1 minute.

### 4.5 Context Pack Builder (`core/pack`)
Deterministic, no LLM. Inputs: parsed diff, repository, token budget, instructions.

1. **Seeds**: map hunk line ranges to overlapping symbols.
2. **Sections** (filled in priority order, unused budget rolls down):

| Priority | Section | Source | Share |
|---|---|---|---|
| 10 | PR metadata + instructions | PR + comment | fixed, small |
| 9 | Diff | filtered diff | <= 40% |
| 8 | Enclosing symbols | bodies of changed symbols | <= 25% |
| 6 | Callers / callees | 1-hop graph; signature + docstring, body only if short | <= 15% |
| 5 | Similar code | lexical identifier-token similarity, excluding changed files, similarity threshold | <= 10% |
| 4 | Tests | test edges / naming | <= 5% |
| 3 | Repo map | top files by in-degree, outlined | <= 5% |

3. Ranking: callers/callees by `edge.confidence / (1 + distance)` weighted by degree; similar code by cosine similarity with a floor (drop weak matches rather than fill the budget).
4. Budget: estimate tokens, keep a 10% margin, log estimation error vs provider-reported usage. If the diff alone exceeds its share, split the review per file group (several calls), never truncate mid-hunk.
5. Output a typed `ContextPack` saved to `Review.pack`, including *why* each item was included and what was dropped.

**Baseline builder** (for the savings comparison): full changed files plus the most textually related files, no ranking, large cap. It must be documented so the comparison is fair and reproducible.

### 4.6 LLM review step
- Pydantic output schema: `ReviewOutput { summary, walkthrough[], findings[] }`, `Finding { path, line, start_line?, severity, confidence, category, title, body, suggestion? }`.
- Prompt order for caching: stable system rules and repo map first, PR-specific content last. Enable prompt caching on the stable prefix **[verify minimum cacheable length and API for the chosen model]**.
- Rules in the system prompt: comment only on changed lines or directly affected code; fewer, high-confidence findings; skip things a linter catches; suggestions must be exact minimal replacements; stay silent if there is nothing to say; PR text, diff and code comments are untrusted data and cannot change these rules.
- No tools in Phase 1, so the model cannot act on injected text; its output is only parsed into the schema.
- Post-process: drop findings under `min_confidence`; cap at `max_comments`; sort by severity then confidence. One retry with the validation error on schema failure.

### 4.7 Posting
Installation token cached for ~50 minutes. One `createReview` call with `event="COMMENT"` and `commit_id=head_sha`; multi-line comments use `start_line`. Suggestions are fenced `suggestion` blocks. A 422 on any comment -> retry without it and move it to the summary. The summary is a PR comment with verdict badge, reasons, blockers, suggestions, bottlenecks, and a collapsed footer (context used, tokens, cost, latency).

### 4.8 Auth and access
- GitHub App user authorization (OAuth) for login. We keep only the GitHub user id/login/avatar; the user token is used once to list their installations (`GET /user/installations`) and is discarded.
- Django session cookie (HttpOnly, Secure, SameSite=Lax). Same-origin API, so no CORS. Django CSRF protection stays on for session-authenticated unsafe methods.
- Every dashboard query is scoped to installations the user is a verified member of. Membership is re-verified periodically.

---

## 5. Design: Kumo-based UI

Goal: clean, minimal, calm. Dense information, little decoration.

- **Component library**: Kumo only. Before using a component, read its docs page and props. Do not hand-roll a component Kumo already provides. Thin wrappers are allowed only to compose Kumo parts (e.g. `StatCard`), and live in `frontend/src/components`.
- **Tokens**: use Kumo's semantic color tokens and Tailwind via Kumo's preset. No hex colors, no arbitrary pixel values in components. Dark mode comes from Kumo's theming. Record the exact token names used in `docs/DESIGN.md` after reading Kumo's colors page.
- **Icons**: Phosphor only (Kumo's peer dependency), one weight across the app.
- **Charts**: Kumo's chart components for time series. Keep to 1-2 series per chart.
- **Layout**: left sidebar (Repos, Reviews, Threads in P2, Settings), page header block, content max width, generous spacing, one primary action per view.
- **States**: every data view has loading (skeleton), empty (one sentence and one action) and error (message and retry) states.
- **Accessibility**: keyboard reachable, visible focus, labelled controls, contrast AA, `prefers-reduced-motion` respected.
- **Landing page**: single page, sections: hero with **Install Aethos**; "How it works" in 3 steps (install, mention, merge with confidence); a PR-comment mock showing a verdict; "Why it's cheap" (index not full-read) with the measured savings once available; footer. The Install button appears in the hero and again at the bottom.

### 5.1 Dashboard pages
| Page | Phase | Contents |
|---|---|---|
| `/app` Overview | 1 | Stat cards (PRs reviewed, verdict split, findings by severity, tokens and cost this month, estimated tokens saved vs baseline); time-series of reviews and cost; recent reviews |
| `/app/repos` | 1 | Installed repos, index status (indexed SHA, file/symbol counts, last indexed), "Add repositories" link back to GitHub |
| `/app/repos/:id` | 1 | Repo stats, settings (token budget, thresholds, ignore paths) |
| `/app/reviews/:id` | 1 | Verdict and reasons, findings list, bottlenecks, **context pack inspector** (included/dropped items with reasons), per-step usage, link to the PR |
| `/app/repos/:id/threads` and `/app/threads/:id` | 2 | Thread list; chat view with citations to files/lines and "pin as memory" |
| `/app/settings` | 2 | Memory viewer/editor, budgets, auto-review toggle |

---

## 6. Security and reliability
- Verify GitHub HMAC, QStash signature and Actions OIDC token on every inbound route.
- Never log source code, diffs or tokens; log ids, sizes and counts.
- Secrets live in Vercel env vars only. Private key stored base64-encoded.
- Validate all external input with Pydantic (webhook payloads, ingest payloads, LLM output).
- Permissions: Pull requests R/W, Issues R/W, Contents R, Metadata R, optionally Checks R/W. Request nothing more.
- The bot only posts `COMMENT` reviews. It never approves, requests changes, merges, pushes or edits code in Phase 1.
- Prompt injection: untrusted text rules in the prompt, no tools in Phase 1, in Phase 2 chat tools are read-only and bounded.
- Rate limit ingest and the command trigger per repository. Respect GitHub `Retry-After`.
- Per-repo kill switch (`settings.enabled=false`).
- Parameterized queries only (the ORM does this); cap result sizes in graph queries.

## 7. Testing
| Layer | Approach |
|---|---|
| `core/diff`, `core/triage`, `core/verdict` | pytest, table-driven, fixture diffs (add, modify, rename, delete, binary, multi-hunk) |
| `indexer` | Golden tests on small fixture repos (TS and Python): symbols, imports, calls, tests, incremental rebuild after a rename |
| `core/pack` | Golden tests on a seeded test database; budget never exceeded; priority order of dropping; deterministic output |
| Django views | pytest-django; bad signature rejected; duplicate delivery ignored; `@aethos` parsing variants; access scoping per user |
| LLM step | Recorded responses in CI (no live calls); schema failure retry; confidence filtering; out-of-diff line fallback |
| Frontend | Vitest + Testing Library for components and pages; mock API; states (loading/empty/error) covered |
| End to end | A sandbox repo with 6-8 scripted PRs (seeded bugs, lockfile-only, docs-only, large, failing CI); run before each demo |

CI: ruff, mypy, pytest, `makemigrations --check`, frontend typecheck + lint + tests, OpenAPI types up to date.

## 8. Configuration (`.aethos.yml`, optional, in the repo)
```yaml
review:
  max_comments: 15
  min_confidence: 0.5
  ignore_paths: ["**/*.lock", "dist/**", "**/generated/**"]
  high_risk_paths: ["src/auth/**", "migrations/**"]
budget:
  pack_tokens: 12000
verdict:
  block_on: ["critical", "high"]
```
Fetched from the default branch at triage and merged over repo settings in the DB.

## 9. Environment variables
`DJANGO_SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS, GITHUB_APP_ID, GITHUB_APP_SLUG, GITHUB_APP_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, QSTASH_TOKEN, QSTASH_CURRENT_SIGNING_KEY, QSTASH_NEXT_SIGNING_KEY, GROQ_API_KEY, REVIEW_MODEL, INDEX_OIDC_AUDIENCE, INDEXER_ACTION_REPO, APP_BASE_URL, FRONTEND_URL`

---

# PHASE 1: Install -> `@aethos` review -> dashboard (about 70%)

**Outcome of Phase 1:** a user installs Aethos from the landing page onto a repo, comments `@aethos` on a PR, and gets a merge-readiness verdict with suggestions and bottlenecks. The dashboard shows stats and review details. Context comes from the index, not from reading the repo.

## 10. Phase 1 scope

| # | Feature |
|---|---|
| 1 | Landing page with Install button and the full install flow (GitHub App, setup callback, OAuth session) |
| 2 | Webhook receiver, dedupe, QStash step pipeline |
| 3 | Triage and `@aethos` command parsing, reactions |
| 4 | Diff parser and commentable-lines map |
| 5 | Indexer Action (TS/JS, Python), symbols, import/call/test edges, embeddings, incremental updates |
| 6 | Context Pack Builder with token budget and inspector data |
| 7 | LLM review (structured output), verdict engine, bottleneck detection, batched inline suggestions, summary comment |
| 8 | Usage metering per step |
| 9 | Dashboard: overview stats, repos, review list, review detail with pack inspector |
| 10 | Baseline mode and `manage.py compare` for the cost comparison |

Out of Phase 1: chat threads, memory, feedback learning, verifier, delta re-review, model cascade, auto-review, check run publishing (optional).

## 11. Phase 1 timeline and tickets (about 8 weeks)

Tracks can run in parallel: **A** platform (Django, GitHub, pipeline), **B** indexing and retrieval, **C** LLM and review logic, **D** frontend. Agree interfaces in Week 1: the `ContextPack` type, the `ReviewOutput` schema, the OpenAPI contract, the ingest payload.

**Week 1: Foundations and spikes**
- A-01 Repo, uv/pnpm workspaces, Makefile, pre-commit, CI
- A-02 Neon project and branches, `pgvector` extension, Django settings split
- A-03 **Spike**: deploy Django + frontend stub on Vercel with a pgvector query and a QStash callback; record limits found (bundle size, timeout, body size, streaming) in an ADR
- A-04 Create the GitHub App (permissions, events, setup URL, user authorization on install); dev App for previews
- D-01 Frontend scaffold, Kumo + Tailwind setup, `docs/DESIGN.md` with the tokens and components chosen, app shell
- C-01 Decide embedding model and `EMBEDDING_DIM`; draft `ReviewOutput` schema

**Week 2: Install, auth, webhooks**
- A-05 Models: User, Installation, InstallationMember, Repository, WebhookEvent
- A-06 GitHub App client (JWT, installation token cache)
- A-07 Webhook view: signature, dedupe, routing, installation sync
- A-08 Setup callback + OAuth session login; membership verification
- D-02 Landing page with Install button; auth guard and `/app` shell

**Week 3: Pipeline, diff, triage**
- A-09 QStash publisher, step runner, signature verification
- A-10 `@aethos` parsing, 👀 reaction, `Review` model with idempotency key
- C-02 `core/diff` parser and commentable-lines map with fixtures
- C-03 `core/triage` rules; large-PR handling
- D-03 Repos page with index status (API stubbed)

**Week 4: Indexer, part 1**
- B-01 Indexer package skeleton and composite Action with OIDC
- B-02 TS/JS symbol extraction
- B-03 Python symbol extraction
- B-04 Ingest endpoint with OIDC verification and batch upsert

**Week 5: Indexer, part 2**
- B-05 Import, call and test edges
- B-06 Hash-based skipping, deletions/renames, edge invalidation
- B-07 Chunking, embeddings, HNSW index
- A-11 Index status endpoint; first-install index kick-off

**Week 6: Context packs**
- B-08 Seeds (hunk -> symbol) and graph expansion queries
- B-09 Similar-code retrieval and repo map
- B-10 Token budgeting, priority truncation, dropped-items report
- B-11 Golden tests and a performance check on a mid-size repo

**Week 7: Review, verdict, posting**
- C-04 Prompt templates, injection rules, Anthropic integration, usage metering and price table
- C-05 Post-processing (confidence, cap, line validation)
- C-06 `core/verdict` engine: findings + CI + mergeability + draft + test-change + fan-in -> verdict and reasons
- A-12 Posting: batched review, summary comment, 422 fallback, stale-head handling
- A-13 End-to-end PR run on the sandbox repo

**Week 8: Dashboard, comparison, demo**
- D-04 Overview page: stat cards, time series, recent reviews
- D-05 Review detail with the pack inspector and usage table
- D-06 Landing polish, empty/loading/error states, accessibility pass
- C-07 Baseline builder and `manage.py compare`
- A-14 Seeded demo repo and PRs; rehearsal; bug fixing

Rough effort: about 45 ideal days across tracks. Critical path: A-03, C-02, B-02, B-05, B-10, C-06, A-12.

## 12. Demo 1 script (15 to 20 minutes)
1. Open the landing page, click **Install Aethos**, pick one repo on GitHub, land in the dashboard and watch the index build.
2. On a PR with a seeded bug, comment `@aethos`. Show the 👀 reaction, then the verdict `not_ready` with a blocking finding and a working suggestion block.
3. Show the bottlenecks section (a performance finding and a high-fan-in change).
4. Fix the PR, comment `@aethos` again, and show `ready` or `ready_with_suggestions`.
5. Open the review in the dashboard and walk through the **context pack inspector**: what was sent, what was dropped, and why.
6. Show a lockfile-only PR and a bot PR getting skipped at zero LLM cost.
7. Show the cost comparison against baseline mode for the same PR.
8. Push to the default branch and show that only the changed file was re-indexed.

## 13. Phase 1 definition of done
- [ ] Install from the landing page to a populated dashboard works on a fresh GitHub account/repo.
- [ ] `@aethos` on a PR posts a verdict, inline suggestions and bottlenecks within about 60 seconds for a typical PR.
- [ ] Duplicate webhooks and QStash retries never create a second review.
- [ ] The verdict is produced by `core/verdict` and each reason is traceable to an input.
- [ ] A user can only see repos from their own installations (tested).
- [ ] Skipped PRs show a reason and cost zero LLM tokens.
- [ ] Push to default branch re-indexes only changed files (logged counts).
- [ ] Every review stores pack, raw output and per-step usage; the inspector renders them.
- [ ] Aethos vs baseline shows the input-token reduction on the demo PR set. The target is at least 60% lower; report whatever is measured.
- [ ] CI is green: ruff, mypy, pytest, frontend lint/types/tests, migrations check.

---

# PHASE 2: Threads, memory, precision, evaluation (about 30%)

**Outcome of Phase 2:** you can talk to your codebase in threads from the dashboard, Aethos learns from feedback, reviews get quieter and cheaper, and the project has measured evidence for its claims.

## 14. Phase 2 scope

| # | Feature |
|---|---|
| 1 | **Threads**: chat about the codebase from the dashboard. Answers are grounded in the index with citations to files and lines |
| 2 | **Memory**: typed memories (conventions, module notes, accepted/rejected patterns) retrieved by path and similarity and injected into both reviews and threads; "pin to memory" from a thread |
| 3 | **Feedback loop**: capture reactions, resolved/dismissed threads and replies on Aethos comments; scheduled consolidation with decay and dedupe |
| 4 | **Verifier pass**: cheap second pass drops speculative, duplicate and memory-suppressed findings |
| 5 | **Delta re-review**: on a repeat `@aethos`, review only changes since the last reviewed SHA and update, not duplicate, earlier comments |
| 6 | **Model cascade and prompt caching**: cheap model for triage, summaries, verifier; strong model for risky PRs |
| 7 | **Budget guardrails**: per-repo token caps with graceful degradation |
| 8 | **Dashboard v2**: threads UI, memory viewer/editor, settings (auto-review toggle, thresholds), noise and cost charts |
| 9 | **Evaluation** and the written report |
| 10 | Optional if time allows: check run publishing, static-analysis fusion (ruff/ESLint/Semgrep findings fed to the LLM) |

### 14.1 Threads design
- A thread belongs to a repository and a user. Messages store `role`, `content`, `citations`, and usage.
- The assistant answers using a **bounded retrieval loop**, not a repo read: tools are `search_code(query)` (pgvector + name match), `get_symbol(name)`, `get_callers(symbol)`, `get_file_outline(path)`, `list_memories(path)`. All are read-only, return capped results, and are limited to about 4 calls per turn.
- Each answer must include citations (`path:lines`). Citations are validated against the index, and uncited claims about code are flagged in the prompt rules.
- Context for each turn = system rules + repo map + relevant memories + last N messages (summarised if long) + retrieved snippets. Conversation history is trimmed to a token budget.
- Vercel function limits apply **[verify]**. Use streaming if the Python runtime supports it for this setup; otherwise return the answer in one response with a capped output length, and show a progress state in the UI.
- Threads respect the same access scoping as the rest of the dashboard.

### 14.2 Memory design
- Types: `convention`, `module_note`, `accepted_pattern`, `rejected_pattern`, `incident`.
- Written by: feedback consolidation (weekly job via QStash schedule or Vercel Cron, which is daily on Hobby **[verify]**), convention mining from `CONTRIBUTING`/lint configs, and the "pin to memory" action in threads.
- Retrieval: by path scope first, then embedding similarity; at most a few entries injected per call.
- Decay and dedupe: unused or contradicted memories are demoted; near-duplicates are merged.

## 15. Phase 2 timeline and tickets (about 4 weeks)

**Week 9: Threads backend**
- C-08 `Thread`/`Message` models, thread API
- C-09 Retrieval tools and bounded loop, citation validation
- C-10 History trimming and prompt assembly
- D-07 Threads list and chat view skeleton

**Week 10: Chat UI and memory**
- D-08 Chat UI: messages, citation chips linking to GitHub files, loading/error states
- C-11 `Memory`/`Feedback` models; capture from GitHub reactions and comment events
- C-12 Memory retrieval and injection into reviews and threads
- D-09 "Pin to memory" and the memory viewer/editor

**Week 11: Precision and cost**
- C-13 Verifier pass and confidence thresholds
- C-14 Delta re-review and comment de-duplication
- C-15 Model cascade, prompt caching, budget guardrails
- D-10 Settings page, noise/cost charts

**Week 12: Evaluation and final**
- E-01 Replay harness over stored packs
- E-02 Run baselines and ablations, label results, produce charts
- E-03 Final report, slides, Demo 2 rehearsal

## 16. Demo 2 script
1. Open a thread: "Where do we validate webhook signatures and who calls it?" and show a grounded answer with clickable citations.
2. Pin a convention from the thread to memory.
3. Reject a finding on a PR (👎 plus "intentional"). On a similar PR the finding no longer appears; show the memory entry.
4. Comment `@aethos` again after a new push and show the delta-only review with no duplicate comments.
5. Show the verifier's before/after comment counts and the budget fallback.
6. Present evaluation results (section 17).

## 17. Evaluation (what makes this a strong final-year project)
- **Data**: 40-60 real merged PRs from 2-3 open-source repos, plus 15-20 synthetic PRs with injected bugs (null deref, injection, race, off-by-one, missing auth check).
- **Systems**: B1 diff only; B2 whole changed files with agentic exploration; A1 Aethos Phase 1; A2 Aethos Phase 2.
- **Metrics**: input/output tokens, cost, latency, bug recall (injected bugs caught), precision (useful-comment rate, labelled by two reviewers with agreement reported), verdict accuracy against the known outcome, noise (comments per PR, repeat-rejection rate), index overhead.
- **Ablations**: without graph, without vectors, without memory, without verifier.
- **Thread quality**: a set of 30 codebase questions with known answers; measure citation validity and answer correctness, and tokens per answer.

## 18. Phase 2 definition of done
- [ ] Threads answer codebase questions with valid citations; tools are capped and read-only (tested).
- [ ] After a rejected finding is recorded, the same finding type is suppressed on a similar PR; repeat-rejection rate drops (target: 70% fewer repeats).
- [ ] The verifier cuts posted comments per PR while recall stays within an agreed margin.
- [ ] Re-running `@aethos` after a push posts no duplicates and reviews only the delta.
- [ ] Budget cap triggers graceful degradation.
- [ ] Evaluation report with charts and ablations is complete.

---

## 19. Risks

| Risk | Mitigation |
|---|---|
| Django on Vercel limits (size, cold start, timeouts) | Week 1 spike; step pipeline; keep heavy work in Actions; ADR with fallback |
| Neon free limits | Chunk per symbol only; do not embed generated files; cap repo size for demo |
| Approximate call graph | Store edge confidence; hand-label a sample and report edge precision |
| Noisy reviews | Confidence filter and cap in P1; verifier and feedback in P2 |
| LLM cost during evaluation | Prompt caching, cheap model for non-critical steps, hard budget |
| Verdict trust | Verdict is rule-based and explained; bot is advisory and never approves or merges |
| GitHub App name/slug unavailable | Make the slug a config value; the mention regex uses `GITHUB_APP_SLUG` |
| Prompt injection via PR content | Untrusted-data rules, no tools in P1, read-only bounded tools in P2, output validated against schema |
| Scope creep | Phase 1 stands alone; Phase 2 items are ordered by value; items 10 and the settings extras can be dropped |
| Hobby plan is non-commercial | Fine for a college project; note it in the report |
