import type { components } from "./api-types";

type Schemas = components["schemas"];

export type Me = Schemas["MeOut"];
export type Overview = Schemas["OverviewOut"];
export type Repo = Schemas["RepoOut"];
export type RepoDetail = Schemas["RepoDetail"];
export type ReviewListItem = Schemas["ReviewListItem"];
export type ReviewDetail = Schemas["ReviewDetail"];
export type Finding = Schemas["FindingOut"];
export type SettingsPatch = Schemas["SettingsPatch"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function readCookie(name: string, source: string = document.cookie): string | null {
  for (const part of source.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

type Method = "GET" | "POST" | "PATCH";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const token = readCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = response.statusText || "Request failed";
    try {
      const data: unknown = await response.json();
      if (data && typeof data === "object" && "detail" in data) {
        const detail = (data as { detail: unknown }).detail;
        if (typeof detail === "string") message = detail;
      }
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export interface ReviewQuery {
  repoId?: number;
  limit?: number;
  offset?: number;
}

function query(params: Record<string, number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  me: () => request<Me>("GET", "/api/auth/me"),
  logout: () => request<{ ok: boolean }>("POST", "/api/auth/logout"),
  overview: (days: number) => request<Overview>("GET", `/api/dashboard/overview${query({ days })}`),
  repos: () => request<Repo[]>("GET", "/api/dashboard/repos"),
  repo: (id: number) => request<RepoDetail>("GET", `/api/dashboard/repos/${id}`),
  updateSettings: (id: number, patch: SettingsPatch) =>
    request<Repo>("PATCH", `/api/dashboard/repos/${id}/settings`, patch),
  reviews: ({ repoId, limit, offset }: ReviewQuery = {}) =>
    request<ReviewListItem[]>(
      "GET",
      `/api/dashboard/reviews${query({ repo_id: repoId, limit, offset })}`,
    ),
  review: (id: number) => request<ReviewDetail>("GET", `/api/dashboard/reviews/${id}`),
};
