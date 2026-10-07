import { Text } from "@cloudflare/kumo";

export interface BarPoint {
  label: string;
  value: number;
}

interface BarSeriesProps {
  points: BarPoint[];
  ariaLabel: string;
}

/** A tiny, dependency-free bar series built from Kumo tokens. */
export function BarSeries({ points, ariaLabel }: BarSeriesProps) {
  const max = Math.max(0, ...points.map((p) => p.value));
  if (max === 0) {
    return (
      <div className="flex h-28 items-center justify-center rounded-md bg-kumo-recessed">
        <Text variant="secondary" size="sm">
          No reviews in this period
        </Text>
      </div>
    );
  }
  return (
    <div role="img" aria-label={ariaLabel} className="flex h-28 items-end gap-0.5">
      {points.map((point) => (
        <div
          key={point.label}
          className="flex h-full min-w-0 flex-1 items-end justify-center"
          title={`${point.label}: ${point.value}`}
        >
          <div
            className={`w-full max-w-4 rounded-sm ${point.value > 0 ? "bg-kumo-brand" : "bg-kumo-hairline"}`}
            style={{ height: point.value > 0 ? `${Math.max(8, (point.value / max) * 100)}%` : "2px" }}
          />
        </div>
      ))}
    </div>
  );
}

/** One point per day for the last `days` days (today included), with zeros where nothing ran. */
export function fillDays(
  series: { date: string; reviews: number }[],
  days: number,
  today: Date = new Date(),
): BarPoint[] {
  const byDate = new Map(series.map((p) => [p.date, p.reviews]));
  const out: BarPoint[] = [];
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const day = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - offset));
    const key = day.toISOString().slice(0, 10);
    out.push({ label: key, value: byDate.get(key) ?? 0 });
  }
  return out;
}
