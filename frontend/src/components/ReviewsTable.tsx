import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TextLink } from "./AppLink";
import { Surface } from "./Surface";
import { Text } from "./Text";
import { GitPullRequestIcon } from "@phosphor-icons/react";
import { formatCompact, formatCost, timeAgo } from "../lib/format";
import type { ReviewListItem } from "../lib/api";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";
import { StatusBadge, VerdictBadge } from "./Badges";

interface ReviewsTableProps {
  reviews: ReviewListItem[];
  showRepo?: boolean;
}

export function ReviewsTable({ reviews, showRepo = true }: ReviewsTableProps) {
  const workspace = useWorkspaceSlug();
  if (reviews.length === 0) {
    return (
      <Surface className="p-2">
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <GitPullRequestIcon size={24} />
            </EmptyMedia>
            <EmptyTitle>No reviews yet</EmptyTitle>
            <EmptyDescription>
              Comment @aethos-agent on a pull request to get a merge-readiness review.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </Surface>
    );
  }
  return (
    <Surface className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Pull request</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Verdict</TableHead>
            <TableHead>Tokens</TableHead>
            <TableHead>Cost</TableHead>
            <TableHead>When</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reviews.map((review) => (
            <TableRow key={review.id}>
              <TableCell>
                <div className="flex min-w-0 flex-col">
                  <TextLink href={workspacePath(workspace, `reviews/${review.id}`)}>
                    {showRepo ? `${review.repo}#${review.pr_number}` : `#${review.pr_number}`}
                  </TextLink>
                  <Text variant="secondary" size="sm" truncate>
                    {review.pr_title || review.skip_reason || "Untitled"}
                  </Text>
                </div>
              </TableCell>
              <TableCell>
                <StatusBadge status={review.status} />
              </TableCell>
              <TableCell>
                {review.verdict ? <VerdictBadge verdict={review.verdict} /> : "–"}
              </TableCell>
              <TableCell>{formatCompact(review.tokens_in + review.tokens_out)}</TableCell>
              <TableCell>{formatCost(review.cost_usd)}</TableCell>
              <TableCell>{timeAgo(review.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Surface>
  );
}
