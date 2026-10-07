import { Banner, Button, Empty, Loader, Select, Sidebar, Text } from "@cloudflare/kumo";
import {
  FolderSimpleIcon,
  GitPullRequestIcon,
  PlusIcon,
  SignOutIcon,
  SquaresFourIcon,
} from "@phosphor-icons/react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Brand } from "../components/Brand";
import { GitHubIcon } from "../components/GitHubIcon";
import { ApiError, type Workspace } from "../lib/api";
import { INSTALL_URL, LOGIN_URL } from "../lib/links";
import { useLogout, useMe, useWorkspaces } from "../lib/queries";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";
import { NotFoundPage } from "../pages/NotFoundPage";

function FullPage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-5">
      <div className="w-full max-w-lg">{children}</div>
    </div>
  );
}

function Loading() {
  return (
    <FullPage>
      <div role="status" aria-label="Loading">
        <Loader size={28} />
      </div>
    </FullPage>
  );
}

function SignIn() {
  return (
    <FullPage>
      <Empty
        icon={<GitHubIcon size={48} />}
        title="Sign in to Aethos"
        description="Use your GitHub account to see the repositories and pull requests Aethos reviews for you."
        contents={
          <Button variant="primary" onClick={() => window.location.assign(LOGIN_URL)}>
            Continue with GitHub
          </Button>
        }
      />
    </FullPage>
  );
}

function Onboarding({ login }: { login: string }) {
  const logout = useLogout();
  return (
    <FullPage>
      <Empty
        icon={<GitHubIcon size={48} />}
        title="Install Aethos on a GitHub account"
        description={`You are signed in as ${login}. Choose a personal account or an organization, then pick the repositories Aethos may review. Each account becomes its own workspace.`}
        contents={
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={() => window.location.assign(INSTALL_URL)}>
              Install on GitHub
            </Button>
            <Button variant="ghost" loading={logout.isPending} onClick={() => logout.mutate()}>
              Sign out
            </Button>
          </div>
        }
      />
    </FullPage>
  );
}

function WorkspaceSwitcher({ workspaces, current }: { workspaces: Workspace[]; current: string }) {
  const navigate = useNavigate();
  const items: Record<string, string> = {};
  for (const workspace of workspaces) items[workspace.login] = workspace.login;
  return (
    <Sidebar.Group>
      <Sidebar.GroupLabel>Workspace</Sidebar.GroupLabel>
      <div className="px-1 pb-1">
        <Select
          aria-label="Workspace"
          className="w-full"
          value={current}
          items={items}
          onValueChange={(value) => {
            if (value) navigate(workspacePath(String(value)));
          }}
        />
      </div>
      <Sidebar.Menu>
        <Sidebar.MenuButton
          icon={PlusIcon}
          tooltip="Add GitHub account"
          onClick={() => window.location.assign(INSTALL_URL)}
        >
          Add GitHub account
        </Sidebar.MenuButton>
      </Sidebar.Menu>
    </Sidebar.Group>
  );
}

function UserRow({ login, avatarUrl }: { login: string; avatarUrl: string }) {
  const logout = useLogout();
  return (
    <div className="flex w-full min-w-0 items-center gap-2 px-2">
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="size-6 shrink-0 rounded-full" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-6 shrink-0 items-center justify-center rounded-full bg-kumo-recessed text-xs font-medium text-kumo-default"
        >
          {login.slice(0, 1).toUpperCase()}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <Text size="sm" truncate>
          {login}
        </Text>
      </div>
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
  );
}

export function AppShell() {
  const me = useMe();
  const workspaces = useWorkspaces();
  const { pathname } = useLocation();
  const slug = useWorkspaceSlug();

  if (me.isPending) return <Loading />;
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <SignIn />;
    return (
      <div className="px-6 py-5">
        <Banner variant="error" title="Could not load your account" description={me.error.message} />
      </div>
    );
  }
  if (workspaces.isPending) return <Loading />;
  if (workspaces.isError) {
    return (
      <div className="px-6 py-5">
        <Banner
          variant="error"
          title="Could not load your workspaces"
          description={workspaces.error.message}
        />
      </div>
    );
  }

  const list = workspaces.data;
  const first = list[0];
  if (!first) return <Onboarding login={me.data.login} />;
  if (pathname.replace(/\/+$/, "") === "/app") {
    return <Navigate to={workspacePath(first.login)} replace />;
  }

  const current = list.find((w) => w.login.toLowerCase() === slug.toLowerCase());
  const base = workspacePath(current?.login ?? first.login);
  const nav = [
    { href: base, label: "Overview", icon: SquaresFourIcon, active: pathname === base },
    {
      href: `${base}/repos`,
      label: "Repositories",
      icon: FolderSimpleIcon,
      active: pathname.startsWith(`${base}/repos`),
    },
    {
      href: `${base}/reviews`,
      label: "Reviews",
      icon: GitPullRequestIcon,
      active: pathname.startsWith(`${base}/reviews`),
    },
  ];

  return (
    <Sidebar.Provider defaultOpen contained className="h-screen min-h-0!">
      <Sidebar>
        <Sidebar.Header>
          <div className="flex w-full items-center justify-between gap-2">
            <Brand />
            <Sidebar.Trigger />
          </div>
        </Sidebar.Header>
        <Sidebar.Content>
          <WorkspaceSwitcher workspaces={list} current={current?.login ?? ""} />
          <Sidebar.Group>
            <Sidebar.GroupLabel>Manage</Sidebar.GroupLabel>
            <Sidebar.Menu>
              {nav.map((item) => (
                <Sidebar.MenuButton
                  key={item.href}
                  icon={item.icon}
                  href={item.href}
                  active={item.active}
                  tooltip={item.label}
                >
                  {item.label}
                </Sidebar.MenuButton>
              ))}
            </Sidebar.Menu>
          </Sidebar.Group>
        </Sidebar.Content>
        <Sidebar.Footer>
          <UserRow login={me.data.login} avatarUrl={me.data.avatar_url} />
        </Sidebar.Footer>
      </Sidebar>
      <main className="h-full min-w-0 flex-1 overflow-y-auto px-5 py-6 md:px-10 md:py-10">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
          <div className="md:hidden">
            <Sidebar.Trigger />
          </div>
          {current ? <Outlet /> : <NotFoundPage />}
        </div>
      </main>
    </Sidebar.Provider>
  );
}
