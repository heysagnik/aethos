import { FolderSimpleIcon, PlusIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { TextLink } from "../components/AppLink";
import { IndexStatusBadge } from "../components/Badges";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/QueryBoundary";
import { SimpleSelect } from "../components/SimpleSelect";
import { Surface } from "../components/Surface";
import { Text } from "../components/Text";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber, shortSha, timeAgo } from "../lib/format";
import { INSTALL_URL } from "../lib/links";
import { useRepos } from "../lib/queries";
import { useWorkspaceSlug, workspacePath } from "../lib/workspace";

const PAGE_SIZES = [10, 25, 50];
const PAGE_SIZE_ITEMS = Object.fromEntries(PAGE_SIZES.map((n) => [String(n), `${n} per page`]));

export function ReposPage() {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(PAGE_SIZES[0] ?? 10);
  const workspace = useWorkspaceSlug();
  const repos = useRepos(workspace);

  return (
    <>
      <PageHeader
        title="Repositories"
        description="Repositories in this account where Aethos is installed."
        actions={
          <Button onClick={() => window.location.assign(INSTALL_URL)}>
            <PlusIcon />
            Add repositories
          </Button>
        }
      />
      <QueryBoundary query={repos}>
        {(items) => {
          if (items.length === 0) {
            return (
              <Surface className="p-2">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FolderSimpleIcon size={24} />
                    </EmptyMedia>
                    <EmptyTitle>No repositories yet</EmptyTitle>
                    <EmptyDescription>
                      Choose which repositories Aethos can review for this account on GitHub.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </Surface>
            );
          }
          const pageCount = Math.max(1, Math.ceil(items.length / perPage));
          const safePage = Math.min(page, pageCount);
          const start = (safePage - 1) * perPage;
          const visible = items.slice(start, start + perPage);
          return (
            <div className="flex flex-col gap-4">
              <Surface className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Repository</TableHead>
                      <TableHead>Index</TableHead>
                      <TableHead>Indexed code</TableHead>
                      <TableHead>Reviews</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visible.map((repo) => (
                      <TableRow key={repo.id}>
                        <TableCell>
                          <div className="flex flex-col">
                            <TextLink href={workspacePath(workspace, `repos/${repo.id}`)}>
                              {repo.full_name}
                            </TextLink>
                            <Text variant="secondary" size="xs">
                              {repo.is_private ? "Private" : "Public"} · {repo.default_branch}
                            </Text>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-1">
                            <IndexStatusBadge status={repo.index_status} />
                            {repo.last_indexed_at ? (
                              <Text variant="secondary" size="xs">
                                {shortSha(repo.indexed_sha)} · {timeAgo(repo.last_indexed_at)}
                              </Text>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          {formatNumber(repo.file_count)} files · {formatNumber(repo.symbol_count)}{" "}
                          symbols
                        </TableCell>
                        <TableCell>{formatNumber(repo.review_count)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Surface>
              {items.length > (PAGE_SIZES[0] ?? 10) ? (
                <nav
                  aria-label="Pagination"
                  className="flex flex-wrap items-center justify-between gap-3"
                >
                  <Text variant="secondary" size="sm">
                    {start + 1}–{start + visible.length} of {items.length}
                  </Text>
                  <div className="flex items-center gap-2">
                    <SimpleSelect
                      aria-label="Repositories per page"
                      className="w-36"
                      value={String(perPage)}
                      items={PAGE_SIZE_ITEMS}
                      onValueChange={(value) => {
                        setPerPage(Number(value));
                        setPage(1);
                      }}
                    />
                    <Button
                      variant="outline"
                      disabled={safePage <= 1}
                      onClick={() => setPage(safePage - 1)}
                    >
                      Previous
                    </Button>
                    <Text variant="secondary" size="sm">
                      {safePage} / {pageCount}
                    </Text>
                    <Button
                      variant="outline"
                      disabled={safePage >= pageCount}
                      onClick={() => setPage(safePage + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </nav>
              ) : null}
            </div>
          );
        }}
      </QueryBoundary>
    </>
  );
}
