import { useMatch } from "react-router-dom";

/** The workspace slug (GitHub account login) in the current dashboard URL, or "". */
export function useWorkspaceSlug(): string {
  const match = useMatch("/app/:workspace/*");
  return match?.params.workspace ?? "";
}

/** Builds a dashboard path inside a workspace, for example workspacePath("acme", "repos/3"). */
export function workspacePath(workspace: string, sub = ""): string {
  const base = `/app/${encodeURIComponent(workspace)}`;
  return sub ? `${base}/${sub}` : base;
}
