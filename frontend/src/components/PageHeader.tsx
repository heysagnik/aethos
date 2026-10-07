import { Text } from "@cloudflare/kumo";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  leading?: ReactNode;
}

export function PageHeader({ title, description, actions, leading }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 pb-2">
      <div className="flex min-w-0 flex-col gap-1.5">
        {leading}
        <Text variant="heading" size="lg" as="h1">
          {title}
        </Text>
        {description ? <Text variant="secondary">{description}</Text> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
