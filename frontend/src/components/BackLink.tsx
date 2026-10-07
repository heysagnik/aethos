import { CaretLeftIcon } from "@phosphor-icons/react";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";
import { TextLink } from "./AppLink";

interface BackLinkProps {
  /** Path inside the workspace, for example "reviews". */
  to: string;
  label: string;
}

export function BackLink({ to, label }: BackLinkProps) {
  const workspace = useWorkspaceSlug();
  return (
    <TextLink href={workspacePath(workspace, to)} className="text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <CaretLeftIcon size={14} aria-hidden="true" />
        {label}
      </span>
    </TextLink>
  );
}
