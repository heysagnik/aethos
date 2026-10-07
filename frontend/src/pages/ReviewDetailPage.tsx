import { ArrowSquareOutIcon, CaretDownIcon } from "@phosphor-icons/react";
import { useParams } from "react-router-dom";
import { LinkButton } from "../components/AppLink";
import { MeterBar } from "../components/MeterBar";
import { Surface } from "../components/Surface";
import { Text } from "../components/Text";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SeverityBadge, StatusBadge, VerdictBadge } from "../components/Badges";
import { BackLink } from "../components/BackLink";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import type { Finding, ReviewDetail } from "../lib/api";
import { formatCost, formatDuration, formatNumber } from "../lib/format";
import { groupBySection, parsePack, SECTION_LABELS } from "../lib/pack";
import { useReview } from "../lib/queries";

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <Surface className="flex flex-col gap-2 px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <Badge variant="outline">{finding.category}</Badge>
        <Text variant="secondary" size="xs">
          confidence {Math.round(finding.confidence * 100)}%
        </Text>
      </div>
      <Text bold>{finding.title}</Text>
      <Text variant="mono-secondary">
        {finding.path}:{finding.line}
        {finding.posted_inline ? "" : " (not attached to a changed line)"}
      </Text>
      <Text variant="secondary">{finding.body}</Text>
      {finding.suggestion ? (
        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs text-foreground">
          {finding.suggestion}
        </pre>
      ) : null}
    </Surface>
  );
}

function Findings({ review }: { review: ReviewDetail }) {
  const bottlenecks = review.findings.filter((f) => f.category === "performance");
  const others = review.findings.filter((f) => f.category !== "performance");
  if (review.findings.length === 0) {
    return (
      <Text variant="secondary">
        {review.status === "posted" ? "No findings were reported." : "No findings yet."}
      </Text>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {bottlenecks.length > 0 ? (
        <section className="flex flex-col gap-4">
          <Text variant="heading">Bottlenecks</Text>
          {bottlenecks.map((f) => (
            <FindingCard key={`${f.path}:${f.line}:${f.title}`} finding={f} />
          ))}
        </section>
      ) : null}
      {others.length > 0 ? (
        <section className="flex flex-col gap-4">
          <Text variant="heading">Findings</Text>
          {others.map((f) => (
            <FindingCard key={`${f.path}:${f.line}:${f.title}`} finding={f} />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function SectionTrigger({ children }: { children: React.ReactNode }) {
  return (
    <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium">
      {children}
      <CaretDownIcon size={14} aria-hidden="true" />
    </CollapsibleTrigger>
  );
}

function PackInspector({ review }: { review: ReviewDetail }) {
  const pack = parsePack(review.pack);
  if (!pack) return <Text variant="secondary">No context pack was built for this review.</Text>;
  const groups = groupBySection(pack.items);
  return (
    <div className="flex flex-col gap-4">
      <MeterBar
        label="Context used"
        value={pack.tokensUsed}
        max={Math.max(pack.budget, 1)}
        valueText={`${formatNumber(pack.tokensUsed)} / ${formatNumber(pack.budget)} tokens`}
      />
      {!pack.indexUsed ? (
        <Alert>
          <AlertTitle>No code index was used</AlertTitle>
          <AlertDescription>
            This review only saw the diff. Set up indexing on the repository page for richer context.
          </AlertDescription>
        </Alert>
      ) : null}
      {!pack.diffComplete ? (
        <Alert>
          <AlertTitle>Part of the diff was not reviewed</AlertTitle>
          <AlertDescription>
            Some changes did not fit the context budget. Raise the budget or review a smaller pull
            request.
          </AlertDescription>
        </Alert>
      ) : null}
      {groups.map(([section, items]) => (
        <Collapsible key={section} defaultOpen={section === "symbols" || section === "related"}>
          <SectionTrigger>
            {SECTION_LABELS[section] ?? section} · {items.length} item(s) ·{" "}
            {formatNumber(items.reduce((sum, item) => sum + item.tokens, 0))} tokens
          </SectionTrigger>
          <CollapsibleContent>
            <div className="flex flex-col gap-2 pt-2">
              {items.map((item) => (
                <div key={item.title} className="flex flex-col gap-1">
                  <Text size="sm" bold>
                    {item.title}
                  </Text>
                  <Text variant="secondary" size="xs">
                    Included because: {item.reason} · {formatNumber(item.tokens)} tokens
                  </Text>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      ))}
      {pack.dropped.length > 0 ? (
        <Collapsible>
          <SectionTrigger>
            Left out to stay within budget · {pack.dropped.length} item(s)
          </SectionTrigger>
          <CollapsibleContent>
            <div className="flex flex-col gap-2 pt-2">
              {pack.dropped.map((item) => (
                <Text key={`${item.section}:${item.title}`} variant="secondary" size="sm">
                  {item.title} ({SECTION_LABELS[item.section] ?? item.section}, {item.reason},{" "}
                  {formatNumber(item.tokens)} tokens)
                </Text>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}

function Usage({ review }: { review: ReviewDetail }) {
  if (review.usage.length === 0) return <Text variant="secondary">No model calls were made.</Text>;
  return (
    <Surface className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Step</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Tokens in</TableHead>
            <TableHead>Tokens out</TableHead>
            <TableHead>Cost</TableHead>
            <TableHead>Time</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {review.usage.map((row, index) => (
            <TableRow key={`${row.step}-${index}`}>
              <TableCell>{row.step}</TableCell>
              <TableCell>{row.model}</TableCell>
              <TableCell>{formatNumber(row.tokens_in)}</TableCell>
              <TableCell>{formatNumber(row.tokens_out)}</TableCell>
              <TableCell>{formatCost(row.cost_usd)}</TableCell>
              <TableCell>{formatDuration(row.duration_ms)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Surface>
  );
}

export function ReviewDetailPage() {
  const params = useParams();
  const id = Number(params.reviewId);
  const review = useReview(Number.isFinite(id) ? id : 0);

  return (
    <QueryBoundary query={review}>
      {(data) => (
        <>
          <PageHeader
            leading={<BackLink to="reviews" label="Reviews" />}
            title={`${data.repo}#${data.pr_number}`}
            description={data.pr_title}
            actions={
              <LinkButton href={data.pr_url} external variant="outline">
                <ArrowSquareOutIcon />
                Open pull request
              </LinkButton>
            }
          />
          <div className="flex flex-col gap-6">
            <Surface className="flex flex-col gap-3 px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <VerdictBadge verdict={data.verdict} />
                <StatusBadge status={data.status} />
                <Badge variant="outline">{data.mode}</Badge>
                {data.risk ? <Badge variant="outline">{data.risk} risk</Badge> : null}
              </div>
              {data.summary ? <Text>{data.summary}</Text> : null}
              {data.skip_reason ? <Text variant="secondary">{data.skip_reason}</Text> : null}
              {data.error ? <Text variant="error">{data.error}</Text> : null}
              {data.verdict_reasons.length > 0 ? (
                <ul className="flex list-disc flex-col gap-1 pl-5">
                  {data.verdict_reasons.map((reason, index) => (
                    <li key={index}>
                      <Text as="span" size="sm">
                        {String(reason.text ?? "")}
                      </Text>
                    </li>
                  ))}
                </ul>
              ) : null}
              {data.instructions ? (
                <Text variant="secondary" size="sm">
                  Requested focus: {data.instructions}
                </Text>
              ) : null}
              <Text variant="secondary" size="xs">
                {formatNumber(data.tokens_in)} tokens in, {formatNumber(data.tokens_out)} out ·{" "}
                {formatCost(data.cost_usd)} · {formatDuration(data.latency_ms)}
              </Text>
            </Surface>

            <Findings review={data} />

            <section className="flex flex-col gap-4">
              <Text variant="heading">Context pack</Text>
              <Surface className="px-5 py-4">
                <PackInspector review={data} />
              </Surface>
            </section>

            <section className="flex flex-col gap-4">
              <Text variant="heading">Model usage</Text>
              <Usage review={data} />
            </section>
          </div>
        </>
      )}
    </QueryBoundary>
  );
}
