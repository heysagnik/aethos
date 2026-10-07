import { Banner, Button, Loader } from "@cloudflare/kumo";
import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

interface QueryBoundaryProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}

/** Renders the loading and error states once so every page handles them the same way. */
export function QueryBoundary<T>({ query, children }: QueryBoundaryProps<T>) {
  if (query.isPending) {
    return (
      <div className="flex justify-center py-16" role="status" aria-label="Loading">
        <Loader size={24} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <Banner
        variant="error"
        title="Something went wrong"
        description={query.error.message}
        action={
          <Button size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }
  return <>{children(query.data)}</>;
}
