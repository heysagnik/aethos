import { Link } from "@cloudflare/kumo";
import { CaretLeftIcon } from "@phosphor-icons/react";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";

interface BackLinkProps {
  /** Path inside the workspace, for example "reviews". */
  to: string;
  label: string;
}

export function BackLink({ to, label }: BackLinkProps) {
  const workspace = useWorkspaceSlug();
  return (
    <Link href={workspacePath(workspace, to)} variant="plain">
      <span className="inline-flex items-center gap-1">
        <CaretLeftIcon size={14} aria-hidden="true" />
        {label}
      </span>
    </Link>
  );
}
