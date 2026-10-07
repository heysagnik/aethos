# AGENT.md: Rules for AI coding agents working on Aethos

Read this file and `PLAN.md` before changing anything. If a task conflicts with either, stop and ask. Do not guess.

Aethos is a GitHub App that reviews PRs on `@aethos` mention. Backend is Django (django-ninja) on Vercel with Neon Postgres. Frontend is a React SPA built with Kumo. See `PLAN.md` for the architecture.

## 1. How to work (the loop)

1. **Read first.** Open the files you will touch, their tests, and one neighbouring file that does something similar. Match what is there.
2. **State a short plan** (3-6 bullets) before editing: files to change, tests to add, anything risky.
3. **Make the smallest change that solves the task.** One concern per change. No drive-by refactors, renames or formatting sweeps in unrelated files.
4. **Write or update tests in the same change.** For a bug fix, write the failing test first.
5. **Run the checks** (section 9). Fix every failure. Never claim success without having run them.
6. **Report honestly.** Say what you changed, what you ran, and what you could not verify. If a check was skipped or failed, say so.

When unsure about a requirement, an API, or a library's behaviour, **look it up or ask**. Do not invent function names, props, endpoints, config keys or package versions. Check the installed package source or official docs, and confirm that a symbol exists before using it.

## 2. Hard rules (never break these)

- Never commit secrets, tokens, private keys, or real `.env` files. Use `.env.example` with placeholders.
- Never log source code, diffs, prompts, tokens or webhook bodies. Log ids, sizes and counts.
- Never trust input from outside: webhook payloads, ingest payloads, PR text, diffs, code comments, LLM output. Validate with Pydantic at the boundary.
- Never make the bot approve, request changes on, merge, push to, or edit a user's repo. Reviews use `event="COMMENT"` only.
- Never build SQL by string formatting. Use the ORM or parameterized queries.
- Never disable signature checks (GitHub HMAC, QStash, OIDC), CSRF, or access scoping to make something work.
- Never skip or weaken tests, lint rules, type checks or pre-commit hooks to get green. Fix the cause.
- Never add a dependency without stating why and checking it is maintained, compatible with our Python/React versions, and licensed compatibly. Prefer the standard library and what is already installed.
- Never edit an applied migration. Add a new one.
- Never run destructive commands (dropping tables, force pushes, deleting branches or data) without explicit approval.

## 3. Backend conventions (Python / Django)

**Versions and tools:** Python 3.12, Django 5.x, django-ninja, Pydantic v2, psycopg 3. Use `uv` for dependencies, `ruff` for lint and format, `mypy` (with django-stubs) for types, `pytest` + `pytest-django` for tests.

**Layering (strict):**
```
api (ninja routers / views)  ->  services.py  ->  selectors.py  ->  models.py
                                      \-> core/ (pure logic)
```
- **Views/routers are thin**: parse and validate input, call one service or selector, return a schema. No business logic, no ORM queries beyond trivial lookups.
- **`services.py`** holds writes and orchestration. Wrap multi-row writes in `transaction.atomic()`. Services take plain arguments and return plain objects or models.
- **`selectors.py`** holds read queries for the API and dashboard. Always scope by the requesting user's installations. Use `select_related` / `prefetch_related` to avoid N+1; add an index for any new filter or order column.
- **`core/`** is pure Python: no Django imports, no network, no database, no clock or randomness without injection. Diff parsing, triage, pack building (given data), verdict, prompt assembly live here and must be fully unit-tested.
- External services (GitHub, Anthropic, QStash, embeddings) are accessed only through small client classes in the owning app, injected into services so tests can fake them.

**Style:**
- Full type hints on all functions, including return types. No `Any` unless unavoidable, with a comment saying why. No bare `# type: ignore`; give the error code and a reason.
- Names say what things are: `commentable_lines`, not `data2`. Functions do one thing and stay short (aim for under 40 lines). Early returns over deep nesting.
- Prefer `dataclass(frozen=True)` or Pydantic models over loose dicts for structured data passed between layers.
- Use `pathlib`, f-strings, `enum.StrEnum` for fixed sets (statuses, verdicts, severities). No magic strings or numbers; define constants once (e.g. `EMBEDDING_DIM`, `MAX_COMMENTS`).
- Comments explain **why**, not what. Public functions get a one-line docstring when the name is not enough. Do not leave commented-out code, TODOs without an issue reference, or debug prints.
- Raise specific exceptions (`class DiffParseError(ValueError)`), never bare `except:` and never swallow errors silently. Catch only what you can handle; let the rest propagate to the step runner, which marks the review failed.
- Time: use timezone-aware datetimes (`django.utils.timezone.now`). Money/cost: `Decimal`.

**Django specifics:**
- Every model has `created_at`/`updated_at` where useful, explicit `related_name`, `__str__`, and `Meta.indexes` / constraints for lookup paths and uniqueness. Idempotency is enforced by **database unique constraints**, not just code checks.
- Migrations: one logical change per migration, named clearly, reviewed, and `makemigrations --check` must pass in CI. Never put data backfills and schema changes in the same migration without reason.
- Settings come from environment variables via one settings module; no `os.environ` reads scattered in app code.
- Serverless: `CONN_MAX_AGE = 0`, use Neon's pooled connection string, no in-process state between requests, no threads or background workers.

**Reliability rules for the pipeline:**
- Every webhook and step handler is **idempotent**: dedupe by delivery id / unique constraint, and safe to run twice.
- Every step is short and does one thing; state is persisted to the database before publishing the next step.
- Before posting to GitHub, re-check the PR head SHA; if it changed, post nothing and mark `superseded`.
- Validate comment lines against the commentable-lines map; never post a comment on a line outside the diff.
- All LLM calls: explicit `max_tokens`, timeout, metered into `UsageLog`, output parsed into a Pydantic model, one retry on validation failure, then fail cleanly.
- The verdict comes from `core/verdict` using structured inputs. Do not let model prose decide it.

## 4. Indexer conventions
- Pure functions for parsing and graph building; I/O only in `upload.py` and the CLI entrypoint.
- Deterministic output: same repo state gives the same symbols, edges and ordering.
- Never crash the whole run on one bad file: record the failure, skip the file, continue, and report counts at the end.
- Treat all repo contents as untrusted. Never execute repo code. Cap file size and skip generated/vendored paths.
- Golden tests with small fixture repos for every supported language and edge kind.

## 5. Frontend conventions (React / TypeScript / Kumo)

**Stack:** Vite, React, TypeScript `strict`, Tailwind CSS, `@cloudflare/kumo`, `@phosphor-icons/react`, React Router, TanStack Query.

**Design consistency (the most important frontend rule):**
- **Use Kumo components.** Before building any UI element, check Kumo's component docs (https://kumo-ui.com). If Kumo has it, use it. Read the component's page for its real props and variants; do not guess prop names.
- Compose Kumo parts into small app components in `frontend/src/components` only when the same combination is used in two or more places.
- **No hard-coded colors, font sizes, radii or shadows.** Use Kumo's semantic tokens and Tailwind utilities mapped to them. If you need a value that does not exist, stop and ask instead of inventing one.
- **Icons:** Phosphor only, one consistent weight and size scale.
- **Spacing and layout:** use the spacing scale only; no arbitrary values like `mt-[13px]`. Reuse the page header and layout components from the app shell so every page looks the same.
- **Theme:** works in light and dark through Kumo theming; never assume a background color.
- Keep the UI minimal: one primary action per view, no decorative elements, restrained motion that respects `prefers-reduced-motion`.
- Record the tokens and components in use in `docs/DESIGN.md` and keep it current. New patterns go there first.
- The app root uses `isolation: isolate` as Kumo requires. Check Kumo's current install docs for any other setup requirements.

**Code rules:**
- Function components and hooks only. One component per file, named exports, file name matches the component.
- Data fetching through TanStack Query hooks in `lib/api`, using types **generated from the backend OpenAPI schema**. Never hand-write types for API responses and never use `any`.
- Every data view implements **loading, empty and error** states.
- Accessibility is not optional: semantic elements, labelled inputs and buttons, keyboard operation, visible focus, AA contrast. Use Kumo's accessible primitives rather than re-implementing them.
- No business logic in components. Format and derive data in small pure functions with tests.
- No `dangerouslySetInnerHTML`. Render Markdown from the backend through a sanitising renderer.
- No secrets in the frontend bundle. Only public config.

## 6. Tests

- Test behaviour, not implementation. Name tests for the scenario: `test_duplicate_delivery_is_ignored`.
- `core/` is covered by fast unit tests with no database. Views and services use `pytest-django`. LLM and GitHub calls are always faked; CI never makes live calls.
- Every bug fix adds a regression test. Every new endpoint tests the success path, validation failure, authorization failure (another user's data) and idempotency where relevant.
- Golden/snapshot tests (pack builder, indexer) must be deterministic. Update a snapshot only when the change is intended, and say so.
- Frontend: Vitest + Testing Library for each page's loading, empty, error and happy states.
- No `sleep`-based or order-dependent tests. No tests that depend on the network.

## 7. Git and change hygiene
- Small, focused commits. Message format: `type(scope): summary` where type is `feat | fix | refactor | test | docs | chore`, e.g. `feat(reviews): add verdict engine`.
- Branch per ticket (`feat/c-06-verdict-engine`). The PR description states what changed, why, how it was tested, and any risk or follow-up.
- Do not mix formatting-only changes with logic changes.
- Update `PLAN.md`/docs/ADRs when a decision changes. Record non-obvious decisions as short ADRs in `docs/adr/`.

## 8. Security checklist (apply to every change)
- [ ] Does it handle untrusted input? Is that input validated at the boundary?
- [ ] Is every dashboard query scoped to the requesting user's installations?
- [ ] Are signatures verified on every inbound endpoint?
- [ ] Could any log line contain code, tokens or personal data?
- [ ] Could this create a duplicate review or comment if run twice?
- [ ] Does the bot gain any new GitHub permission or write capability? If yes, stop and ask.

## 9. Definition of done: run these before saying "done"

```bash
make check      # ruff, ruff format --check, mypy, pytest, makemigrations --check, frontend typecheck + lint + test
```
Individual targets (the Makefile should provide them):
```bash
make lint       # ruff + eslint
make types      # mypy + tsc
make test       # pytest + vitest
make migrations # django makemigrations --check --dry-run
make api-types  # regenerate TS types from OpenAPI; must produce no diff
```
A change is done only when:
- [ ] `make check` passes with no new warnings.
- [ ] New or changed behaviour has tests, and they fail without the change.
- [ ] No new `Any`, `type: ignore`, `eslint-disable`, or skipped tests without a written reason.
- [ ] UI changes follow section 5 and were checked in light and dark, at narrow and wide widths, and by keyboard.
- [ ] Docs, `.env.example` and OpenAPI types are updated if they changed.
- [ ] You can state in the summary what was verified and what was not.

## 10. When to stop and ask
Stop and ask the user before you:
- Change the data model in a way that needs a destructive or non-trivial data migration.
- Add a dependency, a GitHub permission, a new external service, or a new env var with cost implications.
- Change the verdict rules, the review prompt rules, or what the bot is allowed to do on GitHub.
- Deviate from `PLAN.md`, or find that `PLAN.md` is wrong or ambiguous.
- Hit a failing check you cannot fix without weakening a rule.
