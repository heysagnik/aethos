export interface PackItem {
  section: string;
  title: string;
  reason: string;
  tokens: number;
  text: string;
}

export interface DroppedItem {
  section: string;
  title: string;
  reason: string;
  tokens: number;
}

export interface Pack {
  budget: number;
  tokensUsed: number;
  diffComplete: boolean;
  items: PackItem[];
  dropped: DroppedItem[];
  indexUsed: boolean;
  indexSha: string;
}

export const SECTION_LABELS: Record<string, string> = {
  meta: "Pull request",
  diff: "Changes",
  symbols: "Enclosing code",
  related: "Callers and callees",
  similar: "Similar code",
  tests: "Tests",
  map: "Repository map",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readItems<T>(value: unknown, keys: (keyof T & string)[]): T[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => {
    const out: Record<string, unknown> = {};
    for (const key of keys) out[key] = row[key];
    return out as T;
  });
}

/** Validate the loosely typed `pack` JSON from the API into a usable shape. */
export function parsePack(raw: Record<string, unknown> | null | undefined): Pack | null {
  if (!raw) return null;
  const meta = isRecord(raw.meta) ? raw.meta : {};
  return {
    budget: typeof raw.budget === "number" ? raw.budget : 0,
    tokensUsed: typeof raw.tokens_used === "number" ? raw.tokens_used : 0,
    diffComplete: raw.diff_complete !== false,
    items: readItems<PackItem>(raw.items, ["section", "title", "reason", "tokens", "text"]),
    dropped: readItems<DroppedItem>(raw.dropped, ["section", "title", "reason", "tokens"]),
    indexUsed: meta.index_used === true,
    indexSha: typeof meta.index_sha === "string" ? meta.index_sha : "",
  };
}

export function groupBySection(items: PackItem[]): [string, PackItem[]][] {
  const groups = new Map<string, PackItem[]>();
  for (const item of items) {
    const list = groups.get(item.section) ?? [];
    list.push(item);
    groups.set(item.section, list);
  }
  return [...groups.entries()];
}
