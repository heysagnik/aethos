import { Button, Select } from "@cloudflare/kumo";
import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { ReviewsTable } from "../components/ReviewsTable";
import { useRepos, useReviews } from "../lib/queries";

const PAGE_SIZE = 25;

export function ReviewsPage() {
  const [repoId, setRepoId] = useState<number | undefined>(undefined);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const repos = useRepos();
  const reviews = useReviews({ repoId, limit });

  const items: Record<string, string> = { all: "All repositories" };
  for (const repo of repos.data ?? []) items[String(repo.id)] = repo.full_name;

  return (
    <>
      <PageHeader
        title="Reviews"
        description="Every pull request Aethos has been asked to review."
        actions={
          <Select
            aria-label="Filter by repository"
            className="w-56"
            value={repoId === undefined ? "all" : String(repoId)}
            items={items}
            onValueChange={(value) => {
              setLimit(PAGE_SIZE);
              setRepoId(value === null || value === "all" ? undefined : Number(value));
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
              <Button onClick={() => setLimit((current) => current + PAGE_SIZE)}>Show more</Button>
            ) : null}
          </div>
        )}
      </QueryBoundary>
    </>
  );
}
