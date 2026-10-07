import { useState } from "react";
import { MeterBar } from "../components/MeterBar";
import { Surface } from "../components/Surface";
import { Text } from "../components/Text";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { GitHubIcon } from "../components/GitHubIcon";
import { BarSeries, fillDays } from "../components/BarSeries";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { ReviewsTable } from "../components/ReviewsTable";
import { StatCard } from "../components/StatCard";
import { formatCompact, formatCost, formatNumber } from "../lib/format";
import { INSTALL_URL } from "../lib/links";
import { useOverview, useRepos, useReviews } from "../lib/queries";
import { useWorkspaceSlug } from "../lib/workspace";

const RANGES = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

const VERDICT_ROWS = [
  { key: "ready", label: "Ready to merge", tone: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400", bar: "bg-emerald-500" },
  { key: "ready_with_suggestions", label: "Ready, with suggestions", tone: "bg-sky-500/15 text-sky-600 dark:text-sky-400", bar: "bg-sky-500" },
  { key: "not_ready", label: "Not ready", tone: "bg-destructive/15 text-destructive", bar: "bg-destructive" },
  { key: "inconclusive", label: "Inconclusive", tone: "bg-muted text-muted-foreground", bar: "bg-muted-foreground/40" },
] as const;

export function OverviewPage() {
  const [days, setDays] = useState(30);
  const workspace = useWorkspaceSlug();
  const repos = useRepos(workspace);
  const overview = useOverview(workspace, days);
  const recent = useReviews({ workspace, limit: 8 });

  return (
    <>
      <PageHeader
        title="Overview"
        description="How Aethos is reviewing your pull requests."
        actions={
          <Tabs value={String(days)} onValueChange={(value) => setDays(Number(value))}>
            <TabsList>
              {RANGES.map((range) => (
                <TabsTrigger key={range.value} value={range.value}>
                  {range.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        }
      />
      {repos.data && repos.data.length === 0 ? (
        <Surface className="p-2">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <GitHubIcon size={24} />
              </EmptyMedia>
              <EmptyTitle>No repositories yet</EmptyTitle>
              <EmptyDescription>
                Choose repositories for this account on GitHub, then comment @aethos-agent on a pull
                request.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button onClick={() => window.location.assign(INSTALL_URL)}>Add repositories</Button>
            </EmptyContent>
          </Empty>
        </Surface>
      ) : (
        <QueryBoundary query={overview}>
          {(data) => {
            const postedTotal = Math.max(1, data.reviews_posted);
            return (
              <div className="flex flex-col gap-6">
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <StatCard
                    label="Reviews posted"
                    value={formatNumber(data.reviews_posted)}
                    hint={`${formatNumber(data.reviews_skipped)} skipped at no cost`}
                  />
                  <StatCard
                    label="Not ready to merge"
                    value={formatNumber(data.verdicts.not_ready)}
                    hint={`${Math.round((100 * data.verdicts.not_ready) / postedTotal)}% of posted reviews`}
                  />
                  <StatCard
                    label="LLM tokens"
                    value={formatCompact(data.tokens_in + data.tokens_out)}
                    hint={`${formatCompact(data.tokens_in)} in, ${formatCompact(data.tokens_out)} out`}
                  />
                  <StatCard label="LLM cost" value={formatCost(data.cost_usd)} hint={`Last ${data.days} days`} />
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Surface className="flex flex-col justify-between gap-4 px-5 py-4">
                    <Text variant="heading">Verdicts</Text>
                    {VERDICT_ROWS.map((row) => (
                      <div key={row.key} className="flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <Badge variant="secondary" className={row.tone}>
                            {row.label}
                          </Badge>
                          <Text variant="secondary" size="sm">
                            {data.verdicts[row.key]}
                          </Text>
                        </div>
                        <div
                          className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                          role="presentation"
                        >
                          <div
                            className={cn("h-full rounded-full", row.bar)}
                            style={{ width: `${(100 * data.verdicts[row.key]) / postedTotal}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </Surface>

                  <div className="flex flex-col gap-4">
                    <Surface className="flex flex-col gap-3 px-5 py-4">
                      <Text variant="heading">Reviews per day</Text>
                      <BarSeries
                        ariaLabel="Reviews per day"
                        points={fillDays(data.series, days)}
                      />
                    </Surface>
                    <Surface className="flex flex-col gap-3 px-5 py-4">
                      <Text variant="heading">Context savings</Text>
                      {data.savings.saved_pct === null ? (
                        <Text variant="secondary" size="sm">
                          Run the same pull request in baseline mode to see how many input tokens the
                          code index saves. See the README for the compare command.
                        </Text>
                      ) : (
                        <MeterBar
                          label="Input tokens saved vs. baseline"
                          value={Math.max(0, data.savings.saved_pct)}
                          valueText={`${data.savings.saved_pct}%`}
                        />
                      )}
                      {data.savings.pairs > 0 ? (
                        <Text variant="secondary" size="xs">
                          {formatNumber(data.savings.aethos_tokens_in)} tokens vs.{" "}
                          {formatNumber(data.savings.baseline_tokens_in)} across {data.savings.pairs}{" "}
                          pull request(s)
                        </Text>
                      ) : null}
                    </Surface>
                  </div>
                </div>

                <section className="flex flex-col gap-4">
                  <Text variant="heading">Recent reviews</Text>
                  <QueryBoundary query={recent}>
                    {(reviews) => <ReviewsTable reviews={reviews} />}
                  </QueryBoundary>
                </section>
              </div>
            );
          }}
        </QueryBoundary>
      )}
    </>
  );
}
