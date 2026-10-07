import { Surface, Text } from "@cloudflare/kumo";

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
}

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <Surface className="flex flex-col gap-1 px-5 py-4">
      <Text variant="secondary" size="sm">
        {label}
      </Text>
      <Text variant="heading" size="lg" as="p">
        {value}
      </Text>
      {hint ? (
        <Text variant="secondary" size="xs">
          {hint}
        </Text>
      ) : null}
    </Surface>
  );
}
