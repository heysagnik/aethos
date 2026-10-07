import {
  FolderSimpleIcon,
  GitPullRequestIcon,
  PlusIcon,
  SignOutIcon,
  SquaresFourIcon,
} from "@phosphor-icons/react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AppLink } from "../components/AppLink";
import { Brand } from "../components/Brand";
import { GitHubIcon } from "../components/GitHubIcon";
import { SimpleSelect } from "../components/SimpleSelect";
import { Text } from "../components/Text";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, type Workspace } from "../lib/api";
import { INSTALL_URL, LOGIN_URL } from "../lib/links";
import { useLogout, useMe, useWorkspaces } from "../lib/queries";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";
import { NotFoundPage } from "../pages/NotFoundPage";

const COLLAPSED_HIDDEN = "group-data-[collapsible=icon]:hidden";

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
      <div role="status" aria-label="Loading" className="flex justify-center">
        <Spinner className="size-7" />
      </div>
    </FullPage>
  );
}

function SignIn() {
  return (
    <FullPage>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <GitHubIcon size={24} />
          </EmptyMedia>
          <EmptyTitle>Sign in to Aethos</EmptyTitle>
          <EmptyDescription>
            Use your GitHub account to see the repositories and pull requests Aethos reviews for
            you.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={() => window.location.assign(LOGIN_URL)}>Continue with GitHub</Button>
        </EmptyContent>
      </Empty>
    </FullPage>
  );
}

function Onboarding({ login }: { login: string }) {
  const logout = useLogout();
  return (
    <FullPage>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <GitHubIcon size={24} />
          </EmptyMedia>
          <EmptyTitle>Install Aethos on a GitHub account</EmptyTitle>
          <EmptyDescription>
            {`You are signed in as ${login}. Choose a personal account or an organization, then pick the repositories Aethos may review. Each account becomes its own workspace.`}
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="flex-row justify-center">
          <Button onClick={() => window.location.assign(INSTALL_URL)}>Install on GitHub</Button>
          <Button variant="ghost" disabled={logout.isPending} onClick={() => logout.mutate()}>
            Sign out
          </Button>
        </EmptyContent>
      </Empty>
    </FullPage>
  );
}

function WorkspaceSwitcher({ workspaces, current }: { workspaces: Workspace[]; current: string }) {
  const navigate = useNavigate();
  const items: Record<string, string> = {};
  for (const workspace of workspaces) items[workspace.login] = workspace.login;
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Workspace</SidebarGroupLabel>
      <div className={`px-1 pb-1 ${COLLAPSED_HIDDEN}`}>
        <SimpleSelect
          aria-label="Workspace"
          value={current}
          items={items}
          onValueChange={(value) => navigate(workspacePath(value))}
        />
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip="Add GitHub account"
            onClick={() => window.location.assign(INSTALL_URL)}
          >
            <PlusIcon />
            <span>Add GitHub account</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  );
}

function UserRow({ login, avatarUrl }: { login: string; avatarUrl: string }) {
  const logout = useLogout();
  return (
    <div className="flex w-full min-w-0 items-center gap-2 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="size-6 shrink-0 rounded-full" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium"
        >
          {login.slice(0, 1).toUpperCase()}
        </span>
      )}
      <div className={`min-w-0 flex-1 ${COLLAPSED_HIDDEN}`}>
        <Text size="sm" truncate className="block">
          {login}
        </Text>
      </div>
      <Button
        className={COLLAPSED_HIDDEN}
        variant="ghost"
        size="icon-sm"
        aria-label="Sign out"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        <SignOutIcon />
      </Button>
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
        <Alert variant="destructive">
          <AlertTitle>Could not load your account</AlertTitle>
          <AlertDescription>{me.error.message}</AlertDescription>
        </Alert>
      </div>
    );
  }
  if (workspaces.isPending) return <Loading />;
  if (workspaces.isError) {
    return (
      <div className="px-6 py-5">
        <Alert variant="destructive">
          <AlertTitle>Could not load your workspaces</AlertTitle>
          <AlertDescription>{workspaces.error.message}</AlertDescription>
        </Alert>
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
    <SidebarProvider defaultOpen className="fixed inset-0 h-auto min-h-0 overflow-hidden">
      <Sidebar collapsible="icon">
        <SidebarHeader className="h-[58px] flex-row items-center justify-between gap-2 border-b px-3 py-0">
          <div className={COLLAPSED_HIDDEN}>
            <Brand />
          </div>
          <SidebarTrigger />
        </SidebarHeader>
        <SidebarContent>
          <WorkspaceSwitcher workspaces={list} current={current?.login ?? ""} />
          <SidebarGroup>
            <SidebarGroupLabel>Manage</SidebarGroupLabel>
            <SidebarMenu>
              {nav.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={item.active}
                    tooltip={item.label}
                    render={<AppLink href={item.href} />}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="border-t">
          <UserRow login={me.data.login} avatarUrl={me.data.avatar_url} />
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="h-full min-h-0 min-w-0 overflow-hidden">
        <div className="flex h-[58px] shrink-0 items-center border-b bg-background px-5 md:px-10">
          <div className="md:hidden">
            <SidebarTrigger />
          </div>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-5 py-6 md:px-10 md:py-8">
            {current ? <Outlet /> : <NotFoundPage />}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
