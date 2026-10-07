import { Empty, Link, Surface, Table, Text } from "@cloudflare/kumo";
import { GitPullRequestIcon } from "@phosphor-icons/react";
import { formatCompact, formatCost, timeAgo } from "../lib/format";
import type { ReviewListItem } from "../lib/api";
import { StatusBadge, VerdictBadge } from "./Badges";

interface ReviewsTableProps {
  reviews: ReviewListItem[];
  showRepo?: boolean;
}

export function ReviewsTable({ reviews, showRepo = true }: ReviewsTableProps) {
  if (reviews.length === 0) {
    return (
      <Surface className="p-2">
        <Empty
          size="sm"
          icon={<GitPullRequestIcon size={32} />}
          title="No reviews yet"
          description="Comment @aethos on a pull request to get a merge-readiness review."
        />
      </Surface>
    );
  }
  return (
    <Surface className="overflow-x-auto">
      <Table>
        <Table.Header>
          <Table.Row>
            <Table.Head>Pull request</Table.Head>
            <Table.Head>Status</Table.Head>
            <Table.Head>Verdict</Table.Head>
            <Table.Head>Tokens</Table.Head>
            <Table.Head>Cost</Table.Head>
            <Table.Head>When</Table.Head>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {reviews.map((review) => (
            <Table.Row key={review.id}>
              <Table.Cell>
                <div className="flex min-w-0 flex-col">
                  <Link href={`/app/reviews/${review.id}`} variant="plain">
                    {showRepo ? `${review.repo}#${review.pr_number}` : `#${review.pr_number}`}
                  </Link>
                  <Text variant="secondary" size="sm" truncate>
                    {review.pr_title || review.skip_reason || "Untitled"}
                  </Text>
                </div>
              </Table.Cell>
              <Table.Cell>
                <StatusBadge status={review.status} />
              </Table.Cell>
              <Table.Cell>
                {review.verdict ? <VerdictBadge verdict={review.verdict} /> : "–"}
              </Table.Cell>
              <Table.Cell>{formatCompact(review.tokens_in + review.tokens_out)}</Table.Cell>
              <Table.Cell>{formatCost(review.cost_usd)}</Table.Cell>
              <Table.Cell>{timeAgo(review.created_at)}</Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table>
    </Surface>
  );
}
