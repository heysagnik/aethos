import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildPatch, splitList } from "../pages/RepoDetailPage";
import { QueryClient } from "@tanstack/react-query";
import { AppRoutes, Providers } from "./App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AppRoutes />
      </Providers>
    </MemoryRouter>,
  );
}

function mockFetch(routes: Record<string, { status?: number; body: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const route = routes[url] ?? routes[url.split("?")[0] ?? ""];
    if (!route) return new Response(JSON.stringify({ detail: "Not found" }), { status: 404 });
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("landing page", () => {
  it("offers an install button that starts the GitHub install flow", () => {
    renderAt("/");
    const buttons = screen.getAllByRole("link", { name: /install on github/i });
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    for (const button of buttons) expect(button).toHaveAttribute("href", "/api/github/install");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/ready to merge/i);
  });

  it("explains a failed login", () => {
    renderAt("/?error=login_failed");
    expect(screen.getByText(/could not sign you in/i)).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("asks signed-out visitors to sign in", async () => {
    mockFetch({ "/api/auth/me": { status: 401, body: { detail: "Unauthorized" } } });
    renderAt("/app");
    expect(await screen.findByText(/sign in to aethos/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continue with github/i })).toBeInTheDocument();
  });

  it("shows an empty state with an add-repositories action when nothing is installed", async () => {
    mockFetch({
      "/api/auth/me": {
        body: { login: "octo", avatar_url: "", csrf_token: "t", install_url: "https://github.com/apps/aethos/installations/new" },
      },
      "/api/dashboard/repos": { body: [] },
      "/api/dashboard/overview": {
        body: {
          days: 30, reviews_total: 0, reviews_posted: 0, reviews_skipped: 0,
          verdicts: { ready: 0, ready_with_suggestions: 0, not_ready: 0, inconclusive: 0 },
          severities: { critical: 0, high: 0, medium: 0, low: 0, nit: 0 },
          tokens_in: 0, tokens_out: 0, cost_usd: 0, series: [],
          savings: { pairs: 0, baseline_tokens_in: 0, aethos_tokens_in: 0, saved_pct: null },
        },
      },
      "/api/dashboard/reviews": { body: [] },
    });
    renderAt("/app");
    expect(await screen.findByText(/no repositories yet/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add repositories/i })).toBeInTheDocument(),
    );
  });

  it("shows stats and recent reviews", async () => {
    mockFetch({
      "/api/auth/me": { body: { login: "octo", avatar_url: "", csrf_token: "t", install_url: "x" } },
      "/api/dashboard/repos": {
        body: [{ id: 1, full_name: "acme/app", is_private: false, default_branch: "main",
          index_status: "ready", indexed_sha: "abcdef1234", last_indexed_at: null, file_count: 4,
          symbol_count: 9, edge_count: 3, chunk_count: 9, embedded_count: 9, review_count: 2, settings: {} }],
      },
      "/api/dashboard/overview": {
        body: {
          days: 30, reviews_total: 2, reviews_posted: 2, reviews_skipped: 1,
          verdicts: { ready: 1, ready_with_suggestions: 0, not_ready: 1, inconclusive: 0 },
          severities: { critical: 0, high: 1, medium: 0, low: 0, nit: 0 },
          tokens_in: 2000, tokens_out: 400, cost_usd: 0.0021,
          series: [{ date: "2026-01-01", reviews: 2, cost_usd: 0.0021 }],
          savings: { pairs: 1, baseline_tokens_in: 5000, aethos_tokens_in: 1000, saved_pct: 80 },
        },
      },
      "/api/dashboard/reviews": {
        body: [{ id: 5, repo_id: 1, repo: "acme/app", pr_number: 7, pr_title: "Add cache", pr_url: "u",
          status: "posted", verdict: "not_ready", mode: "aethos", risk: "low", skip_reason: "",
          tokens_in: 1000, tokens_out: 200, cost_usd: 0.001, latency_ms: 1200,
          created_at: new Date().toISOString() }],
      },
    });
    renderAt("/app");
    expect(await screen.findByText("Reviews posted")).toBeInTheDocument();
    expect(await screen.findByText("acme/app#7")).toBeInTheDocument();
    expect(screen.getAllByText("Not ready").length).toBeGreaterThan(0);
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("shows an error with a retry action when the API fails", async () => {
    mockFetch({
      "/api/auth/me": { body: { login: "octo", avatar_url: "", csrf_token: "t", install_url: "x" } },
      "/api/dashboard/repos": { status: 500, body: { detail: "Database unavailable" } },
    });
    renderAt("/app/repos");
    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Database unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("settings form helpers", () => {
  it("splits comma-separated lists", () => {
    expect(splitList(" dist/**, , **/*.gen.ts ,")).toEqual(["dist/**", "**/*.gen.ts"]);
    expect(splitList("")).toEqual([]);
  });

  it("builds a numeric patch", () => {
    const patch = buildPatch({
      enabled: true, mode: "aethos", maxComments: "10", minConfidence: "0.6",
      packTokens: "9000", ignorePaths: "a/**", highRiskPaths: "",
    });
    expect(patch).toEqual({
      enabled: true, mode: "aethos", max_comments: 10, min_confidence: 0.6, pack_tokens: 9000,
      ignore_paths: ["a/**"], high_risk_paths: [],
    });
  });
});
