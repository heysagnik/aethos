import { Badge } from "@cloudflare/kumo";
import type { ComponentProps } from "react";

type Variant = ComponentProps<typeof Badge>["variant"];

interface Descriptor {
  label: string;
  variant: Variant;
}

const VERDICTS: Record<string, Descriptor> = {
  ready: { label: "Ready to merge", variant: "success" },
  ready_with_suggestions: { label: "Ready, with suggestions", variant: "info" },
  not_ready: { label: "Not ready", variant: "error" },
  inconclusive: { label: "Inconclusive", variant: "neutral" },
};

const STATUSES: Record<string, Descriptor> = {
  posted: { label: "Posted", variant: "success" },
  skipped: { label: "Skipped", variant: "secondary" },
  superseded: { label: "Superseded", variant: "secondary" },
  failed: { label: "Failed", variant: "error" },
  queued: { label: "In progress", variant: "info" },
  triaged: { label: "In progress", variant: "info" },
  packed: { label: "In progress", variant: "info" },
  reviewed: { label: "In progress", variant: "info" },
};

const INDEX_STATUSES: Record<string, Descriptor> = {
  ready: { label: "Index ready", variant: "success" },
  indexing: { label: "Indexing", variant: "info" },
  pending: { label: "Not indexed", variant: "warning" },
  failed: { label: "Index failed", variant: "error" },
};

const SEVERITIES: Record<string, Variant> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
  nit: "neutral",
};

export function verdictLabel(verdict: string): string {
  return VERDICTS[verdict]?.label ?? "No verdict";
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const entry = VERDICTS[verdict];
  return <Badge variant={entry?.variant ?? "secondary"}>{entry?.label ?? "No verdict"}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const entry = STATUSES[status] ?? { label: status, variant: "secondary" as Variant };
  return <Badge variant={entry.variant}>{entry.label}</Badge>;
}

export function IndexStatusBadge({ status }: { status: string }) {
  const entry = INDEX_STATUSES[status] ?? { label: status, variant: "secondary" as Variant };
  return <Badge variant={entry.variant}>{entry.label}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={SEVERITIES[severity] ?? "neutral"}>{severity}</Badge>;
}
