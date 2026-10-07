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
| **Groq** | The LLM that writes the review | Yes, rate limited |

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

### Groq (LLM)
1. Create an API key at console.groq.com.

| Variable | Value |
|---|---|
| `GROQ_API_KEY` **SECRET** | your key |
| `REVIEW_MODEL` | default `llama-3.3-70b-versatile`. Any Groq chat model that supports JSON mode works. Check Groq's current model list and prices first. |

The price table in `backend/aethos/settings/base.py` (`LLM_PRICES`) drives the cost figures shown in the dashboard. Update it if you change model or if Groq's prices change. An unknown model shows a cost of $0.

### Embeddings (no account needed)
Embeddings power the "similar existing code" part of each review. They use the BAAI **bge-base-en-v1.5** model (768 dimensions), which the GitHub Action indexer runs on the Actions runner itself (via `fastembed`, no API key, no hosted service). The vectors are uploaded with the code chunks and stored in Neon with pgvector. At review time Aethos searches with the stored vectors of the code being changed, so nothing is embedded on Vercel.

- The first indexing run downloads the model (~200 MB, cached between runs by the Action) and embeds every chunk; later runs embed only changed files.
- Set the workflow input `embed: "false"` to skip embeddings. Aethos then uses keyword matching.
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
| `INDEX_OIDC_AUDIENCE` | same as `APP_BASE_URL` |
| `INDEXER_ACTION_REPO` | `<github user>/<this repo>/action`, shown to users in the indexing snippet |

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
3. Open the site, click **Install on GitHub**, pick one repository, finish. You should land on the dashboard.

## 4. Build the code index (once per repository)

Aethos works without an index but then only sees the diff. To give it codebase context, add this to the repository as `.github/workflows/aethos-index.yml` (the dashboard's repository page shows a copy-paste version with your values filled in):

```yaml
name: Aethos index
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  id-token: write
jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: <github user>/<this repo>/action@main
        with:
          api-url: https://<your domain>
```

The repository that contains `action/` must be reachable by the installing repository (public, or internal/private with Actions access granted). Run the workflow once with **Run workflow**; the dashboard then shows the index as ready.

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

- [ ] **Vercel Python limits.** Function duration (set to 60 s in `vercel.json`; Hobby may cap lower), bundle size, and that the `/api/(.*)` rewrite hands Django the original request path. If requests 404 inside Django, this is the first place to look.
- [ ] **QStash delivery.** A comment should produce four step calls (`triage`, `pack`, `review`, `post`). Signature verification uses `APP_BASE_URL` + the request path, so `APP_BASE_URL` must be the exact public URL.
- [ ] **GitHub OIDC for the indexer.** The token audience must equal `INDEX_OIDC_AUDIENCE`. The Action requests it for `--api-url`, so they match when `INDEX_OIDC_AUDIENCE` equals `APP_BASE_URL`.
- [ ] **Groq JSON mode.** The review call asks for a JSON object. If your chosen model rejects `response_format`, pick another model or tell me; the fallback is prompt-only JSON, which the parser already handles.
- [ ] **Groq rate limits.** Free keys have per-minute token limits. A 12,000-token context fits, but concurrent reviews can hit `429`; QStash will retry the step.
- [ ] **Embeddings.** After the first index, the repository page should say all code chunks have embeddings. If not, check the Action log for "Embedded N code chunk(s)" (the model download or `fastembed` install may have failed; the index still uploads without vectors).
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
