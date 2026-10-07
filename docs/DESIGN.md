# Frontend design notes

The UI uses [Kumo](https://kumo-ui.com) (`@cloudflare/kumo` 2.14) on Tailwind v4. Read this before adding a screen, and update it when you introduce a new pattern.

## Setup facts (verified against the installed package)

- `src/styles/index.css` loads Kumo's styles **before** Tailwind and adds the `@source` line for Kumo's compiled files. Do not reorder them.
- `#root` has `isolation: isolate` (Kumo needs it for floating layers).
- Dark mode: Kumo reads the `data-mode` attribute. `App.tsx` sets it from `prefers-color-scheme`. There are no `dark:` classes anywhere.
- Routing: `LinkProvider` is given `AppLink` (`components/AppLink.tsx`), so Kumo `Link` and `Sidebar.MenuButton` navigate client-side. URLs starting with `/api/` or `http(s)://` stay plain anchors, which is how the Install button reaches the backend.
- `Text` does not accept `className`; wrap it in an element for layout. Monospace variants do not take `size`.

## Tokens in use

Only Kumo semantic tokens, never raw colours: `bg-kumo-brand`, `bg-kumo-recessed`, `text-kumo-default`, `text-kumo-subtle`, `text-kumo-link`, `border-kumo-hairline`. Status colour comes from `Badge`/`Banner`/`Meter` variants.

## Components in use

`Badge`, `Banner`, `Button`, `Collapsible`, `Empty`, `Input`, `LinkButton`, `Link`, `Loader`, `Meter`, `Select`, `Sidebar`, `Surface`, `Switch`, `Table`, `Tabs`, `Text`, `Toasty` with `useKumoToastManager`. Icons are Phosphor (`@phosphor-icons/react`), regular weight, `*Icon` names.

## App components (`src/components`)

| Component | Purpose |
|---|---|
| `PageHeader` | Page title, description and actions; every dashboard page starts with it |
| `StatCard` | One metric on a `Surface` |
| `QueryBoundary` | Shared loading (Loader) and error (Banner with retry) handling for a query |
| `ReviewsTable` | Reviews list with empty state, used on three pages |
| `Badges` | Maps verdicts, review status, index status and severity to Badge variants |
| `BarSeries` | Dependency-free bar chart from Kumo tokens (Kumo's chart needs ECharts; skipped to keep the bundle small) |
| `Brand`, `AppLink` | Logo lockup; router bridge |

## Patterns

- Every data view has loading, empty and error states. Use `QueryBoundary` and an `Empty` with one action.
- One primary action per view (`Button variant="primary"`).
- API types are generated from the backend: `make api-types`. Never hand-write response types.
- The dashboard is lazy-loaded (`App.tsx`) so the landing page stays small.
