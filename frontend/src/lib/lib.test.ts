import { describe, expect, it } from "vitest";
import { readCookie } from "./api";
import { formatCompact, formatCost, formatDuration, shortSha, timeAgo } from "./format";
import { groupBySection, parsePack } from "./pack";

describe("format", () => {
  it("formats costs, durations and counts", () => {
    expect(formatCost(0)).toBe("$0");
    expect(formatCost(0.00123)).toBe("$0.0012");
    expect(formatCost(1.5)).toBe("$1.50");
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatCompact(12_500)).toBe("12.5K");
    expect(shortSha("0123456789abcdef")).toBe("0123456");
  });

  it("describes relative time", () => {
    const now = new Date("2026-01-01T12:00:00Z");
    expect(timeAgo("2026-01-01T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2026-01-01T11:30:00Z", now)).toBe("30 min ago");
    expect(timeAgo("2026-01-01T07:00:00Z", now)).toBe("5 h ago");
    expect(timeAgo("2025-12-30T12:00:00Z", now)).toBe("2 d ago");
  });
});

describe("readCookie", () => {
  it("reads and decodes a named cookie", () => {
    expect(readCookie("csrftoken", "a=1; csrftoken=abc%20def; b=2")).toBe("abc def");
    expect(readCookie("missing", "a=1")).toBeNull();
  });
});

describe("parsePack", () => {
  it("returns null without a pack", () => {
    expect(parsePack(null)).toBeNull();
  });

  it("validates a loosely typed pack", () => {
    const pack = parsePack({
      budget: 1000,
      tokens_used: 400,
      diff_complete: false,
      meta: { index_used: true, index_sha: "abc" },
      items: [
        { section: "diff", title: "a.py hunk 1", reason: "changed", tokens: 100, text: "x" },
        { section: "diff", title: "b.py hunk 1", reason: "changed", tokens: 50, text: "y" },
        { section: "map", title: "map", reason: "orient", tokens: 10, text: "z" },
        "garbage",
      ],
      dropped: [{ section: "tests", title: "t", reason: "total budget", tokens: 9 }],
    });
    expect(pack).not.toBeNull();
    expect(pack?.diffComplete).toBe(false);
    expect(pack?.indexUsed).toBe(true);
    expect(pack?.items).toHaveLength(3);
    expect(pack?.dropped[0]?.reason).toBe("total budget");
    expect(groupBySection(pack?.items ?? []).map(([name, rows]) => [name, rows.length])).toEqual([
      ["diff", 2],
      ["map", 1],
    ]);
  });

  it("tolerates missing fields", () => {
    const pack = parsePack({});
    expect(pack).toMatchObject({ budget: 0, tokensUsed: 0, diffComplete: true, items: [] });
  });
});
