import { useState } from "react";
import { SimpleSelect } from "../components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { ReviewsTable } from "../components/ReviewsTable";
import { useRepos, useReviews } from "../lib/queries";
import { useWorkspaceSlug } from "../lib/workspace";

const PAGE_SIZE = 25;

export function ReviewsPage() {
  const [repoId, setRepoId] = useState<number | undefined>(undefined);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const workspace = useWorkspaceSlug();
  const repos = useRepos(workspace);
  const reviews = useReviews({ workspace, repoId, limit });

  const items: Record<string, string> = { all: "All repositories" };
  for (const repo of repos.data ?? []) items[String(repo.id)] = repo.full_name;

  return (
    <>
      <PageHeader
        title="Reviews"
        description="Every pull request Aethos has been asked to review."
        actions={
          <SimpleSelect
            aria-label="Filter by repository"
            className="w-56"
            value={repoId === undefined ? "all" : String(repoId)}
            items={items}
            onValueChange={(value) => {
              setLimit(PAGE_SIZE);
              setRepoId(value === "all" ? undefined : Number(value));
            }}
          />
        }
      />
      <QueryBoundary query={reviews}>
        {(rows) => (
          <div className="flex flex-col items-start gap-4">
            <div className="w-full">
              <ReviewsTable reviews={rows} />
            </div>
            {rows.length >= limit ? (
              <Button variant="outline" onClick={() => setLimit((current) => current + PAGE_SIZE)}>
                Show more
              </Button>
            ) : null}
          </div>
        )}
      </QueryBoundary>
    </>
  );
}
