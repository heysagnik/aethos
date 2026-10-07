import { Button, Empty, Link, Surface, Table, Text } from "@cloudflare/kumo";
import { FolderSimpleIcon, PlusIcon } from "@phosphor-icons/react";
import { IndexStatusBadge } from "../components/Badges";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { formatNumber, shortSha, timeAgo } from "../lib/format";
import { INSTALL_URL } from "../lib/links";
import { useRepos } from "../lib/queries";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";

export function ReposPage() {
  const workspace = useWorkspaceSlug();
  const repos = useRepos(workspace);

  return (
    <>
      <PageHeader
        title="Repositories"
        description="Repositories in this account where Aethos is installed."
        actions={
          <Button icon={<PlusIcon />} onClick={() => window.location.assign(INSTALL_URL)}>
            Add repositories
          </Button>
        }
      />
      <QueryBoundary query={repos}>
        {(items) =>
          items.length === 0 ? (
            <Surface className="p-2">
              <Empty
                icon={<FolderSimpleIcon size={40} />}
                title="No repositories yet"
                description="Choose which repositories Aethos can review for this account on GitHub."
              />
            </Surface>
          ) : (
            <Surface className="overflow-x-auto">
              <Table>
                <Table.Header>
                  <Table.Row>
                    <Table.Head>Repository</Table.Head>
                    <Table.Head>Index</Table.Head>
                    <Table.Head>Indexed code</Table.Head>
                    <Table.Head>Reviews</Table.Head>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {items.map((repo) => (
                    <Table.Row key={repo.id}>
                      <Table.Cell>
                        <div className="flex flex-col">
                          <Link href={workspacePath(workspace, `repos/${repo.id}`)} variant="plain">
                            {repo.full_name}
                          </Link>
                          <Text variant="secondary" size="xs">
                            {repo.is_private ? "Private" : "Public"} · {repo.default_branch}
                          </Text>
                        </div>
                      </Table.Cell>
                      <Table.Cell>
                        <div className="flex flex-col gap-1">
                          <IndexStatusBadge status={repo.index_status} />
                          {repo.last_indexed_at ? (
                            <Text variant="secondary" size="xs">
                              {shortSha(repo.indexed_sha)} · {timeAgo(repo.last_indexed_at)}
                            </Text>
                          ) : null}
                        </div>
                      </Table.Cell>
                      <Table.Cell>
                        {formatNumber(repo.file_count)} files · {formatNumber(repo.symbol_count)}{" "}
                        symbols
                      </Table.Cell>
                      <Table.Cell>{formatNumber(repo.review_count)}</Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table>
            </Surface>
          )
        }
      </QueryBoundary>
    </>
  );
}
