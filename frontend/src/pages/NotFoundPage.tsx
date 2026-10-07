import { Empty, LinkButton } from "@cloudflare/kumo";
import { CompassIcon } from "@phosphor-icons/react";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-5">
      <Empty
        icon={<CompassIcon size={48} />}
        title="Page not found"
        description="The page you are looking for does not exist."
        contents={<LinkButton href="/app">Go to the dashboard</LinkButton>}
      />
    </div>
  );
}
