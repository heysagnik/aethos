import { ArrowSquareOutIcon, CopyIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "sonner";
import { useParams } from "react-router-dom";
import { LinkButton } from "../components/AppLink";
import { IndexStatusBadge } from "../components/Badges";
import { Field } from "../components/Field";
import { SimpleSelect } from "../components/SimpleSelect";
import { Surface } from "../components/Surface";
import { Text } from "../components/Text";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { BackLink } from "../components/BackLink";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { ReviewsTable } from "../components/ReviewsTable";
import type { RepoDetail, SettingsPatch } from "../lib/api";
import { formatNumber, shortSha, timeAgo } from "../lib/format";
import { useRepo, useReviews, useUpdateSettings } from "../lib/queries";
import { useWorkspaceSlug } from "../lib/workspace";

export function splitList(text: string): string[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

interface FormState {
  enabled: boolean;
  mode: string;
  maxComments: string;
  minConfidence: string;
  packTokens: string;
  ignorePaths: string;
  highRiskPaths: string;
}

function initialState(repo: RepoDetail): FormState {
  const s = repo.settings;
  const list = (value: unknown) => (Array.isArray(value) ? value.join(", ") : "");
  return {
    enabled: s.enabled !== false,
    mode: s.mode === "baseline" ? "baseline" : "aethos",
    maxComments: String(s.max_comments ?? 15),
    minConfidence: String(s.min_confidence ?? 0.5),
    packTokens: String(s.pack_tokens ?? 12000),
    ignorePaths: list(s.ignore_paths),
    highRiskPaths: list(s.high_risk_paths),
  };
}

export function buildPatch(state: FormState): SettingsPatch {
  return {
    enabled: state.enabled,
    mode: state.mode,
    max_comments: Number(state.maxComments),
    min_confidence: Number(state.minConfidence),
    pack_tokens: Number(state.packTokens),
    ignore_paths: splitList(state.ignorePaths),
    high_risk_paths: splitList(state.highRiskPaths),
  };
}

function SettingsForm({ repo }: { repo: RepoDetail }) {
  const [state, setState] = useState<FormState>(() => initialState(repo));
  const update = useUpdateSettings(repo.id);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setState((current) => ({ ...current, [key]: value }));

  const save = () =>
    update.mutate(buildPatch(state), {
      onSuccess: () => toast.success("Settings saved"),
      onError: (error) => toast.error("Could not save settings", { description: error.message }),
    });

  return (
    <Surface className="flex flex-col gap-4 px-5 py-4">
      <Text variant="heading">Review settings</Text>
      <div className="flex items-center gap-2">
        <Switch
          id="repo-enabled"
          checked={state.enabled}
          onCheckedChange={(checked) => set("enabled", checked)}
        />
        <Label htmlFor="repo-enabled">Respond to @aethos-agent mentions</Label>
      </div>
      <Field label="Context mode">
        <SimpleSelect
          className="w-72"
          value={state.mode}
          items={{
            aethos: "Aethos (indexed context)",
            baseline: "Baseline (whole files, for comparison)",
          }}
          onValueChange={(value) => set("mode", value)}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Max inline comments">
        <Input
          type="number"
          min={1}
          max={50}
          value={state.maxComments}
          onChange={(event) => set("maxComments", event.target.value)}
        />
        </Field>
        <Field label="Min confidence (0 to 1)">
        <Input
          type="number"
          step="0.05"
          min={0}
          max={1}
          value={state.minConfidence}
          onChange={(event) => set("minConfidence", event.target.value)}
        />
        </Field>
        <Field label="Context budget (tokens)">
        <Input
          type="number"
          min={2000}
          max={100000}
          value={state.packTokens}
          onChange={(event) => set("packTokens", event.target.value)}
        />
        </Field>
      </div>
      <Field
        label="Ignore paths"
        description="Comma-separated globs, for example dist/**, **/*.generated.ts"
      >
        <Input
          value={state.ignorePaths}
          onChange={(event) => set("ignorePaths", event.target.value)}
        />
      </Field>
      <Field
        label="High-risk paths"
        description="Changes here raise the review risk, for example src/auth/**"
      >
        <Input
          value={state.highRiskPaths}
          onChange={(event) => set("highRiskPaths", event.target.value)}
        />
      </Field>
      <div>
        <Button disabled={update.isPending} onClick={save}>
          Save settings
        </Button>
      </div>
    </Surface>
  );
}

function IndexCard({ repo }: { repo: RepoDetail }) {
  const copy = () => {
    void navigator.clipboard
      .writeText(repo.index_workflow)
      .then(() => toast.success("Workflow copied"))
      .catch(() => toast.error("Could not copy"));
  };
  return (
    <Surface className="flex flex-col gap-4 px-5 py-4">
      <div className="flex items-center justify-between gap-2">
        <Text variant="heading">Code index</Text>
        <IndexStatusBadge status={repo.index_status} />
      </div>
      {repo.index_status === "ready" ? (
        <>
        <Text variant="secondary" size="sm">
          {formatNumber(repo.file_count)} files, {formatNumber(repo.symbol_count)} symbols and{" "}
          {formatNumber(repo.edge_count)} dependencies at {shortSha(repo.indexed_sha)}
          {repo.last_indexed_at ? `, updated ${timeAgo(repo.last_indexed_at)}` : ""}. Pushes to{" "}
          {repo.default_branch} refresh only the files that changed.
        </Text>
        <Text variant="secondary" size="sm">
          {repo.chunk_count === 0
            ? "No code chunks yet."
            : repo.embedded_count >= repo.chunk_count
              ? `Semantic search is ready: all ${formatNumber(repo.chunk_count)} code chunks have embeddings.`
              : `Semantic search covers ${formatNumber(repo.embedded_count)} of ${formatNumber(repo.chunk_count)} code chunks. Re-run the indexing workflow with embeddings enabled; the rest use keyword matching.`}
        </Text>
        </>
      ) : (
        <Alert>
          <AlertTitle>Add the indexing workflow</AlertTitle>
          <AlertDescription>
            {`Until the index is built, Aethos reviews only the diff. Add this file as .github/workflows/aethos-index.yml on ${repo.default_branch}; it runs on every push.`}
          </AlertDescription>
        </Alert>
      )}
      <details className="group">
        <summary className="cursor-pointer text-foreground underline-offset-4 hover:underline">
          <Text as="span" variant="body" size="sm">
            Show indexing workflow
          </Text>
        </summary>
        <div className="mt-3 flex flex-col gap-2">
          <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs text-foreground">
            {repo.index_workflow}
          </pre>
          <div>
            <Button size="sm" variant="outline" onClick={copy}>
              <CopyIcon />
              Copy workflow
            </Button>
          </div>
        </div>
      </details>
    </Surface>
  );
}

export function RepoDetailPage() {
  const params = useParams();
  const id = Number(params.repoId);
  const repo = useRepo(Number.isFinite(id) ? id : 0);
  const workspace = useWorkspaceSlug();
  const reviews = useReviews({ workspace, repoId: id, limit: 10 });

  return (
    <QueryBoundary query={repo}>
      {(data) => (
        <>
          <PageHeader
            leading={<BackLink to="repos" label="Repositories" />}
            title={data.full_name}
            description={`${data.is_private ? "Private" : "Public"} repository on ${data.default_branch}`}
            actions={
              <LinkButton href={`https://github.com/${data.full_name}`} external variant="outline">
                <ArrowSquareOutIcon />
                Open on GitHub
              </LinkButton>
            }
          />
          <div className="flex flex-col gap-6">
            <IndexCard repo={data} />
            <SettingsForm key={data.id} repo={data} />
            <section className="flex flex-col gap-4">
              <Text variant="heading">Recent reviews</Text>
              <QueryBoundary query={reviews}>
                {(rows) => <ReviewsTable reviews={rows} showRepo={false} />}
              </QueryBoundary>
            </section>
          </div>
        </>
      )}
    </QueryBoundary>
  );
}
