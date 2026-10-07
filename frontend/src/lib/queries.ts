import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type ReviewQuery, type SettingsPatch } from "./api";

export const keys = {
  me: ["me"] as const,
  workspaces: ["workspaces"] as const,
  overview: (workspace: string, days: number) => ["overview", workspace, days] as const,
  repos: (workspace: string) => ["repos", workspace] as const,
  repo: (id: number) => ["repo", id] as const,
  reviews: (query: ReviewQuery) => ["reviews", query] as const,
  review: (id: number) => ["review", id] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: api.me,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 5 * 60_000,
  });
}

export function useWorkspaces() {
  return useQuery({
    queryKey: keys.workspaces,
    queryFn: api.workspaces,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
}

export function useOverview(workspace: string, days: number) {
  return useQuery({
    queryKey: keys.overview(workspace, days),
    queryFn: () => api.overview(workspace, days),
  });
}

export function useRepos(workspace: string) {
  return useQuery({ queryKey: keys.repos(workspace), queryFn: () => api.repos(workspace) });
}

export function useRepo(id: number) {
  return useQuery({ queryKey: keys.repo(id), queryFn: () => api.repo(id), enabled: id > 0 });
}

export function useReviews(query: ReviewQuery = {}) {
  return useQuery({ queryKey: keys.reviews(query), queryFn: () => api.reviews(query) });
}

export function useReview(id: number) {
  return useQuery({ queryKey: keys.review(id), queryFn: () => api.review(id), enabled: id > 0 });
}

export function useUpdateSettings(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.updateSettings(id, patch),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.repo(id) });
      void client.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      client.clear();
      window.location.assign("/");
    },
  });
}
