import { CompassIcon } from "@phosphor-icons/react";
import { LinkButton } from "../components/AppLink";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-5">
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <CompassIcon size={24} />
          </EmptyMedia>
          <EmptyTitle>Page not found</EmptyTitle>
          <EmptyDescription>The page you are looking for does not exist.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <LinkButton href="/app">Go to the dashboard</LinkButton>
        </EmptyContent>
      </Empty>
    </div>
  );
}
