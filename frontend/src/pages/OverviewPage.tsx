import { Badge, Button, Empty, Meter, Surface, Tabs, Text } from "@cloudflare/kumo";
import { useState } from "react";
import { GitHubIcon } from "../components/GitHubIcon";
import { BarSeries } from "../components/BarSeries";
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
  { key: "ready", label: "Ready to merge", variant: "success" },
  { key: "ready_with_suggestions", label: "Ready, with suggestions", variant: "info" },
  { key: "not_ready", label: "Not ready", variant: "error" },
  { key: "inconclusive", label: "Inconclusive", variant: "neutral" },
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
          <Tabs
            variant="segmented"
            size="sm"
            tabs={RANGES}
            value={String(days)}
            onValueChange={(value) => setDays(Number(value))}
          />
        }
      />
      {repos.data && repos.data.length === 0 ? (
        <Surface className="p-2">
          <Empty
            icon={<GitHubIcon size={40} />}
            title="No repositories yet"
            description="Choose repositories for this account on GitHub, then comment @aethos-agent on a pull request."
            contents={
              <Button variant="primary" onClick={() => window.location.assign(INSTALL_URL)}>
                Add repositories
              </Button>
            }
          />
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
                  <Surface className="flex flex-col gap-4 px-4 py-3">
                    <Text variant="heading">Verdicts</Text>
                    {VERDICT_ROWS.map((row) => (
                      <div key={row.key} className="flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <Badge variant={row.variant}>{row.label}</Badge>
                          <Text variant="secondary" size="sm">
                            {data.verdicts[row.key]}
                          </Text>
                        </div>
                        <Meter
                          label={row.label}
                          showValue={false}
                          value={(100 * data.verdicts[row.key]) / postedTotal}
                        />
                      </div>
                    ))}
                  </Surface>

                  <div className="flex flex-col gapx-4 py-3">
                    <Surface className="flex flex-col gap-3 px-4 py-3">
                      <Text variant="heading">Reviews per day</Text>
                      <BarSeries
                        ariaLabel="Reviews per day"
                        points={data.series.map((p) => ({ label: p.date, value: p.reviews }))}
                      />
                    </Surface>
                    <Surface className="flex flex-col gap-3 px-4 py-3">
                      <Text variant="heading">Context savings</Text>
                      {data.savings.saved_pct === null ? (
                        <Text variant="secondary" size="sm">
                          Run the same pull request in baseline mode to see how many input tokens the
                          code index saves. See the README for the compare command.
                        </Text>
                      ) : (
                        <Meter
                          label="Input tokens saved vs. baseline"
                          value={Math.max(0, data.savings.saved_pct)}
                          customValue={`${data.savings.saved_pct}%`}
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

                <section className="flex flex-col gap-3">
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
