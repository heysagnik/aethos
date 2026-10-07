# What Aethos needs from you

The code is finished and tested with fakes. To run it for real you need five accounts and a handful of secrets. Nothing below has been run against the live services, because I don't have your keys, so the first real run is also the first integration test. Section 6 lists what to check on that run.

You give me (or put in Vercel's environment settings) the values marked **SECRET**. Never commit them. `.env.example` lists every variable.

---

## 1. Accounts

| Service | Used for | Free tier is enough? |
|---|---|---|
| **GitHub** | Hosting the GitHub App, OAuth login, the code | Yes |
| **Vercel** | Hosts the dashboard (static) and the Django API (Python function) | Yes (Hobby, non-commercial use) |
| **Neon** | Postgres database | Yes |
| **Upstash** | QStash: delivers each review step as a short request | Yes |

## 2. Create the resources and collect the values

### Neon (database)
1. Create a project and a database.
2. Copy the **pooled** connection string (the host contains `-pooler`) and make sure it ends with `?sslmode=require`.

| Variable | Value |
|---|---|
| `DATABASE_URL` **SECRET** | the pooled connection string |

### Upstash QStash (queue)
1. Create a QStash project.
2. From its dashboard copy the token and both signing keys.

| Variable | Value |
|---|---|
| `QSTASH_TOKEN` **SECRET** | QStash token |
| `QSTASH_CURRENT_SIGNING_KEY` **SECRET** | current signing key |
| `QSTASH_NEXT_SIGNING_KEY` **SECRET** | next signing key |
| `QUEUE_MODE` | `qstash` |

### NVIDIA NIM (review model and embeddings)
One NVIDIA key covers both. The review is written by `nvidia/nemotron-3-super-120b-a12b` through NIM chat completions (`REVIEW_MODEL`, `LLM_TIMEOUT_SECONDS`). Cost figures in the dashboard come from `LLM_PRICES` in `backend/aethos/settings/base.py`; an unlisted model shows $0.

Embeddings power the "similar existing code" part of each review. Aethos embeds every code chunk while indexing with `nvidia/nemotron-3-embed-1b` (2048 dimensions) through NVIDIA's hosted API, and stores the vectors in Neon with pgvector (a `halfvec` column). At review time it searches with the stored vectors of the code being changed.

1. Create an API key at https://build.nvidia.com.

| Variable | Value |
|---|---|
| `NVIDIA_API_KEY` **SECRET** | your key (starts with `nvapi-`) |
| `EMBEDDING_MODEL` | default `nvidia/nemotron-3-embed-1b` |

- Without a key, indexing still works and reviews use keyword matching.
- New files in a PR have no stored vectors yet, so reviews of PRs that only add files use keyword matching.

### Vercel (hosting)
1. Import the repository. Framework preset: **Other**. Root directory: the repository root.
2. `vercel.json` already sets the build command, output directory, the API rewrite and the function entry point.
3. Note your production domain, for example `aethos.vercel.app`.

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `aethos.settings.prod` |
| `DJANGO_SECRET_KEY` **SECRET** | a long random string (`python -c "import secrets;print(secrets.token_urlsafe(60))"`) |
| `ALLOWED_HOSTS` | your domain, for example `aethos.vercel.app` |
| `APP_BASE_URL` | `https://<your domain>` |
| `FRONTEND_URL` | same as `APP_BASE_URL` |

### GitHub App (the bot)
Create it at GitHub → Settings → Developer settings → GitHub Apps → New. Use these settings exactly:

| Setting | Value |
|---|---|
| GitHub App name | `Aethos` (or anything free). The **slug** GitHub assigns is what people type after `@`. If `aethos` is taken, use another name and set `GITHUB_APP_SLUG` to its slug. |
| Homepage URL | `https://<your domain>` |
| Callback URL | `https://<your domain>/api/auth/callback` |
| Request user authorization (OAuth) during installation | **On** |
| Setup URL | `https://<your domain>/api/github/setup` |
| Redirect on update | On |
| Webhook → Active | On |
| Webhook URL | `https://<your domain>/api/github/webhook` |
| Webhook secret | a random string; this is `GITHUB_WEBHOOK_SECRET` |
| Where can this app be installed | Any account (or only yours while testing) |

Repository permissions (nothing else is needed, and Aethos never writes code):

| Permission | Access | Why |
|---|---|---|
| Contents | Read | read `.aethos.yml` and, in baseline mode, file contents |
| Pull requests | Read and write | read the diff, post the review |
| Issues | Read and write | post PR comments, react to the trigger comment |
| Checks | Read | read CI results for the merge verdict |
| Commit statuses | Read | read CI results for the merge verdict |
| Metadata | Read | required by GitHub |

Subscribe to events: **Issue comment**. (Installation events are delivered to every App automatically.)

After creating it:
1. Note the **App ID** and generate a **Client secret** (the Client ID is on the same page).
2. Generate a **private key**; a `.pem` file downloads.

| Variable | Value |
|---|---|
| `GITHUB_APP_ID` | the App ID |
| `GITHUB_APP_SLUG` | the slug, from the App's public URL `github.com/apps/<slug>` |
| `GITHUB_CLIENT_ID` | Client ID |
| `GITHUB_CLIENT_SECRET` **SECRET** | Client secret |
| `GITHUB_WEBHOOK_SECRET` **SECRET** | the webhook secret you chose |
| `GITHUB_APP_PRIVATE_KEY` **SECRET** | the PEM text, or `base64 -w0 key.pem` of it (either is accepted) |

## 3. First deployment

1. Put all the variables above into Vercel (Project → Settings → Environment Variables) and deploy.
2. Create the database tables once, from your machine:
   ```bash
   cp .env.example .env   # fill it in, or export the variables
   uv sync
   DJANGO_SETTINGS_MODULE=aethos.settings.prod uv run python backend/manage.py migrate
   ```
   (Run `migrate` again after any release that adds a migration.)
3. Open the site and click **Sign in with GitHub**. A new user is asked to install the app: pick an account and its repositories, finish, and you land in that account's workspace. Use **Add GitHub account** in the sidebar to add more workspaces.

## 4. The code index

Aethos works without an index but then only sees the diff. The server builds the index itself, so there is nothing to add to your repositories:

- When you install the app or add repositories, each one is indexed automatically.
- Every push to the default branch re-indexes it. This needs the **Push** event: in the GitHub App's settings, under **Permissions & events > Subscribe to events**, tick **Push** (the app also needs **Contents: Read-only**).
- The repository page has an **Index now / Re-index** button.

The page shows the index as ready as soon as the code is parsed, then reports embedding progress while NVIDIA NIM vectors are filled in.

## 5. Use it

Comment on a pull request:

```
@aethos
@aethos focus on security
```

Optional per-repository config in `.aethos.yml` on the default branch:

```yaml
review:
  max_comments: 15
  min_confidence: 0.5
  ignore_paths: ["**/generated/**"]
  high_risk_paths: ["src/auth/**"]
budget:
  pack_tokens: 12000
verdict:
  block_on: [critical, high]
```

Compare Aethos with the naive baseline on a PR (prints tokens, cost and latency, posts nothing):

```bash
DJANGO_SETTINGS_MODULE=aethos.settings.prod uv run python backend/manage.py compare --repo owner/name --pr 12
```

Inspect what was sent to the model for any review: `manage.py show_review <id>` (or the review page in the dashboard).

## 6. Things to check on the first real run

I could not verify these without live credentials. Each is a one-line fix if the service behaves differently from its documentation.

- [ ] **Vercel Python limits.** Function duration (set to 300 s in `vercel.json`; Hobby may cap lower), bundle size, and that the `/api/(.*)` rewrite hands Django the original request path. If requests 404 inside Django, this is the first place to look.
- [ ] **QStash delivery.** A comment should produce four step calls (`triage`, `pack`, `review`, `post`). Signature verification uses `APP_BASE_URL` + the request path, so `APP_BASE_URL` must be the exact public URL.
- [ ] **Indexing.** Index a repository from its page. A run is one `index` step followed by `embed` steps; if a large repository times out, raise `maxDuration` in `vercel.json` or lower `INDEX_MAX_FILES`. The GitHub App must have **Contents: Read-only** and subscribe to **Push**.
- [ ] **Review model JSON mode.** The review call asks for a JSON object (`response_format`). If NIM rejects it for your model, tell me; the parser already handles fenced JSON and strips `<think>` blocks. Nemotron is a reasoning model, so check latency against `LLM_TIMEOUT_SECONDS` and Vercel's `maxDuration`.
- [ ] **NIM rate limits.** Hosted NIM keys are rate limited; concurrent reviews can hit `429`, and QStash retries the step.
- [ ] **Embeddings.** After indexing, the repository page should report all code chunks embedded. If not, check the `embed` step logs (a missing or invalid `NVIDIA_API_KEY`, or NIM rate limits; steps retry through QStash). I could not confirm NVIDIA's exact request fields from its docs, so check the first real call.
- [ ] **pgvector on Neon.** The migration runs `CREATE EXTENSION IF NOT EXISTS vector`; I tested the migration, HNSW index and nearest-neighbour query on a local Postgres 16-series build with pgvector 0.6.2 but not on Neon itself.
- [ ] **Neon cold start.** The first request after idle can take a second or two.
- [ ] **Dashboard look.** The frontend builds, type-checks and passes its tests, but I have not looked at it in a browser. Open `/` and `/app` in light and dark mode and tell me what to adjust.

## 7. Local development (no cloud needed except for real GitHub traffic)

```bash
uv sync
cd frontend && pnpm install && cd ..
make dev-backend    # Django on :8000 (SQLite, steps run inline, no QStash)
make dev-frontend   # Vite on :5173, proxies /api to Django
make check          # lint, types, tests, migrations check, frontend checks
```

To receive real webhooks locally, expose port 8000 with a tunnel (smee.io or ngrok), point the GitHub App's webhook, callback and setup URLs at it, and set `APP_BASE_URL`/`FRONTEND_URL` to the tunnel URL (the Vite dev server on :5173 proxies `/api`, so for OAuth use the tunnel URL for Django directly).
