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
  const max = Math.max(1, ...points.map((p) => p.value));
  return (
    <div role="img" aria-label={ariaLabel} className="flex h-28 items-end gap-1">
      {points.map((point) => (
        <div
          key={point.label}
          className="flex h-full flex-1 flex-col items-center justify-end gap-1"
          title={`${point.label}: ${point.value}`}
        >
          <div
            className="w-full rounded-sm bg-kumo-brand"
            style={{ height: `${Math.max(4, (point.value / max) * 100)}%` }}
          />
        </div>
      ))}
      {points.length === 0 ? <Text variant="secondary">No data yet</Text> : null}
    </div>
  );
}
