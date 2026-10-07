import {
  GitPullRequestIcon,
  SealCheckIcon,
} from "@phosphor-icons/react";
import { useSearchParams } from "react-router-dom";
import { LinkButton } from "../components/AppLink";
import { Brand } from "../components/Brand";
import { Surface } from "../components/Surface";
import { Text } from "../components/Text";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { GitHubIcon } from "../components/GitHubIcon";
import { LOGIN_URL } from "../lib/links";
import { useMe } from "../lib/queries";

const ERRORS: Record<string, string> = {
  login_failed: "We could not sign you in with GitHub. Please try again.",
  install_failed: "The installation could not be completed. Please try again.",
};

const STEPS = [
  {
    icon: GitHubIcon,
    title: "Sign in and install",
    body: "Sign in with GitHub, then add Aethos to the accounts and repositories you choose. Each account gets its own workspace.",
  },
  {
    icon: GitPullRequestIcon,
    title: "Mention",
    body: "Comment @aethos-agent on any pull request, optionally with a focus such as security or performance.",
  },
  {
    icon: SealCheckIcon,
    title: "Merge with confidence",
    body: "Get a clear verdict, inline suggestions you can apply in one click, and the bottlenecks worth fixing first.",
  },
] as const;

function SignInButton({ size = "lg" }: { size?: "default" | "lg" }) {
  const me = useMe();
  const signedIn = me.isSuccess;
  return (
    <LinkButton href={signedIn ? "/app" : LOGIN_URL} size={size}>
      <GitHubIcon />
      {signedIn ? "Open dashboard" : "Sign in with GitHub"}
    </LinkButton>
  );
}

export function LandingPage() {
  const [params] = useSearchParams();
  const error = ERRORS[params.get("error") ?? ""];

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-16 px-6 py-6 md:px-8">
      <nav className="flex items-center justify-between" aria-label="Main">
        <Brand />
        <SignInButton size="default" />
      </nav>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <header className="flex flex-col items-start gap-6 pt-2">
        <Badge variant="outline">Pull request reviews for GitHub</Badge>
        <div className="flex max-w-2xl flex-col gap-3">
          <Text variant="heading1" as="h1">
            Know if a pull request is ready to merge.
          </Text>
          <Text variant="secondary">
            Mention @aethos-agent on a pull request. It reviews the change using an index of your
            codebase, so it understands the surrounding code without reading all of it.
          </Text>
        </div>
        <SignInButton />
      </header>

      <section aria-label="Example review">
        <Surface className="flex flex-col gap-3 px-6 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Text bold>aethos-agent</Text>
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
        <Text variant="heading2" as="h2" id="how-title">
          How it works
        </Text>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <Surface key={step.title} className="flex flex-col gap-2 px-5 py-4">
              <step.icon size={24} className="text-orange-500" aria-hidden="true" />
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
    </div>
  );
}
