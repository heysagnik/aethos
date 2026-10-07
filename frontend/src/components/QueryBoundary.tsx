import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
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
        <Spinner className="size-6" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Something went wrong</AlertTitle>
        <AlertDescription>{query.error.message}</AlertDescription>
        <AlertAction>
          <Button size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </AlertAction>
      </Alert>
    );
  }
  return <>{children(query.data)}</>;
}
