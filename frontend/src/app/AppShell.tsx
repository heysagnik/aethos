import { Banner, Button, Empty, Loader, Sidebar, Text } from "@cloudflare/kumo";
import {
  FolderSimpleIcon,
  GitPullRequestIcon,
  GithubLogoIcon,
  SignOutIcon,
  SquaresFourIcon,
} from "@phosphor-icons/react";
import { Outlet, useLocation } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useLogout, useMe } from "../lib/queries";
import { Brand } from "../components/Brand";

const NAV = [
  { href: "/app", label: "Overview", icon: SquaresFourIcon, match: (p: string) => p === "/app" },
  {
    href: "/app/repos",
    label: "Repositories",
    icon: FolderSimpleIcon,
    match: (p: string) => p.startsWith("/app/repos"),
  },
  {
    href: "/app/reviews",
    label: "Reviews",
    icon: GitPullRequestIcon,
    match: (p: string) => p.startsWith("/app/reviews"),
  },
] as const;

function SignIn() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Empty
        icon={<GithubLogoIcon size={48} />}
        title="Sign in to Aethos"
        description="Use your GitHub account to see the repositories and pull requests Aethos reviews for you."
        contents={
          <Button variant="primary" onClick={() => window.location.assign("/api/auth/login")}>
            Continue with GitHub
          </Button>
        }
      />
    </div>
  );
}

export function AppShell() {
  const me = useMe();
  const logout = useLogout();
  const { pathname } = useLocation();

  if (me.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading">
        <Loader size={28} />
      </div>
    );
  }
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <SignIn />;
    return (
      <div className="p-6">
        <Banner variant="error" title="Could not load your account" description={me.error.message} />
      </div>
    );
  }

  return (
    <Sidebar.Provider defaultOpen>
      <Sidebar>
        <Sidebar.Header>
          <Brand />
        </Sidebar.Header>
        <Sidebar.Content>
          <Sidebar.Group>
            <Sidebar.Menu>
              {NAV.map((item) => (
                <Sidebar.MenuButton
                  key={item.href}
                  icon={item.icon}
                  href={item.href}
                  active={item.match(pathname)}
                >
                  {item.label}
                </Sidebar.MenuButton>
              ))}
            </Sidebar.Menu>
          </Sidebar.Group>
        </Sidebar.Content>
        <Sidebar.Footer>
          <div className="flex items-center justify-between gap-2">
            <Text variant="secondary" size="sm" truncate>
              {me.data.login}
            </Text>
            <Button
              variant="ghost"
              shape="square"
              size="sm"
              aria-label="Sign out"
              icon={<SignOutIcon />}
              loading={logout.isPending}
              onClick={() => logout.mutate()}
            />
          </div>
        </Sidebar.Footer>
      </Sidebar>
      <main className="min-w-0 flex-1 p-6 md:p-8">
        <div className="mx-auto flex max-w-5xl flex-col gap-6">
          <div className="md:hidden">
            <Sidebar.Trigger />
          </div>
          <Outlet />
        </div>
      </main>
    </Sidebar.Provider>
  );
}
