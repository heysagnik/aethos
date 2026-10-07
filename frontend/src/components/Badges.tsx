import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Variant = "success" | "info" | "error" | "warning" | "neutral" | "secondary";

const TONES: Record<Variant, string> = {
  success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  info: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  error: "bg-destructive/15 text-destructive",
  warning: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  neutral: "bg-muted text-muted-foreground",
  secondary: "bg-secondary text-secondary-foreground",
};

function Tone({ variant, children }: { variant: Variant; children: ReactNode }) {
  return (
    <Badge variant="secondary" className={cn(TONES[variant])}>
      {children}
    </Badge>
  );
}

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
  return <Tone variant={entry?.variant ?? "secondary"}>{entry?.label ?? "No verdict"}</Tone>;
}

export function StatusBadge({ status }: { status: string }) {
  const entry = STATUSES[status] ?? { label: status, variant: "secondary" as Variant };
  return <Tone variant={entry.variant}>{entry.label}</Tone>;
}

export function IndexStatusBadge({ status }: { status: string }) {
  const entry = INDEX_STATUSES[status] ?? { label: status, variant: "secondary" as Variant };
  return <Tone variant={entry.variant}>{entry.label}</Tone>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Tone variant={SEVERITIES[severity] ?? "neutral"}>{severity}</Tone>;
}
