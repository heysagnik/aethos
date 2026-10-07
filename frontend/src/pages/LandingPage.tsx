import { Badge, Banner, LinkButton, Surface, Text } from "@cloudflare/kumo";
import {
  GithubLogoIcon,
  GitPullRequestIcon,
  MagnifyingGlassIcon,
  SealCheckIcon,
  StackIcon,
} from "@phosphor-icons/react";
import { useSearchParams } from "react-router-dom";
import { Brand } from "../components/Brand";

const INSTALL_URL = "/api/github/install";

const ERRORS: Record<string, string> = {
  login_failed: "We could not sign you in with GitHub. Please try again.",
  install_failed: "The installation could not be completed. Please try again.",
};

const STEPS = [
  {
    icon: GithubLogoIcon,
    title: "Install",
    body: "Add Aethos to the repositories you choose. It asks for read access to code and permission to comment on pull requests.",
  },
  {
    icon: GitPullRequestIcon,
    title: "Mention",
    body: "Comment @aethos on any pull request, optionally with a focus such as security or performance.",
  },
  {
    icon: SealCheckIcon,
    title: "Merge with confidence",
    body: "Get a clear verdict, inline suggestions you can apply in one click, and the bottlenecks worth fixing first.",
  },
] as const;

const REASONS = [
  {
    icon: StackIcon,
    title: "Indexed, not re-read",
    body: "Your code is parsed once into symbols and dependencies, then updated only for the files that change.",
  },
  {
    icon: MagnifyingGlassIcon,
    title: "Only the relevant context",
    body: "Each review gets the changed code plus its callers, callees and tests, not the whole repository.",
  },
  {
    icon: SealCheckIcon,
    title: "A verdict you can explain",
    body: "Readiness comes from findings, CI status, conflicts and test coverage, and every reason is listed.",
  },
] as const;

function InstallButton({ size = "lg" }: { size?: "base" | "lg" }) {
  return (
    <LinkButton href={INSTALL_URL} variant="primary" size={size} icon={<GithubLogoIcon />}>
      Install on GitHub
    </LinkButton>
  );
}

export function LandingPage() {
  const [params] = useSearchParams();
  const error = ERRORS[params.get("error") ?? ""];

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-20 px-6 py-6">
      <nav className="flex items-center justify-between" aria-label="Main">
        <Brand />
        <div className="flex items-center gap-2">
          <LinkButton href="/app" variant="ghost">
            Dashboard
          </LinkButton>
          <InstallButton size="base" />
        </div>
      </nav>

      {error ? <Banner variant="error" title="Something went wrong" description={error} /> : null}

      <header className="flex flex-col items-start gap-6 pt-6">
        <Badge variant="outline">Pull request reviews for GitHub</Badge>
        <div className="flex max-w-2xl flex-col gap-3">
          <Text variant="heading" size="lg" as="h1">
            Know if a pull request is ready to merge.
          </Text>
          <Text variant="secondary" size="lg">
            Mention @aethos on a pull request. It reviews the change using an index of your
            codebase, so it understands the surrounding code without reading all of it.
          </Text>
        </div>
        <InstallButton />
      </header>

      <section aria-label="Example review">
        <Surface className="flex flex-col gap-3 p-6">
          <div className="flex flex-wrap items-center gap-2">
            <Text bold>aethos</Text>
            <Badge variant="secondary">bot</Badge>
            <Text variant="secondary" size="sm">
              commented on #128
            </Text>
          </div>
          <Text variant="heading" as="h2">
            Aethos: Not ready to merge
          </Text>
          <Text variant="secondary">
            The new retry loop can block the request thread when the upstream is slow.
          </Text>
          <ul className="flex list-disc flex-col gap-1 pl-5">
            <li>
              <Text as="span" size="sm">
                Blocking: retries run synchronously inside the request handler (billing/charge.py).
              </Text>
            </li>
            <li>
              <Text as="span" size="sm">
                Bottleneck: one query per invoice line inside a loop.
              </Text>
            </li>
            <li>
              <Text as="span" size="sm">
                Suggestion: add a test for the timeout path. CI is green.
              </Text>
            </li>
          </ul>
        </Surface>
      </section>

      <section id="how" className="flex flex-col gap-6" aria-labelledby="how-title">
        <Text variant="heading" size="lg" as="h2" id="how-title">
          How it works
        </Text>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <Surface key={step.title} className="flex flex-col gap-2 p-5">
              <step.icon size={24} className="text-kumo-brand" aria-hidden="true" />
              <Text bold>
                {index + 1}. {step.title}
              </Text>
              <Text variant="secondary" size="sm">
                {step.body}
              </Text>
            </Surface>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-6" aria-labelledby="why-title">
        <Text variant="heading" size="lg" as="h2" id="why-title">
          Fast and inexpensive by design
        </Text>
        <div className="grid gap-4 md:grid-cols-3">
          {REASONS.map((reason) => (
            <Surface key={reason.title} className="flex flex-col gap-2 p-5">
              <reason.icon size={24} className="text-kumo-brand" aria-hidden="true" />
              <Text bold>{reason.title}</Text>
              <Text variant="secondary" size="sm">
                {reason.body}
              </Text>
            </Surface>
          ))}
        </div>
      </section>

      <section className="flex flex-col items-start gap-4 pb-8" aria-label="Get started">
        <Text variant="heading" size="lg" as="h2">
          Add Aethos to your next pull request.
        </Text>
        <InstallButton />
      </section>

      <footer className="border-t border-kumo-hairline py-6">
        <Text variant="secondary" size="sm">
          Aethos only comments on pull requests. It never approves, merges or changes your code.
        </Text>
      </footer>
    </div>
  );
}
