import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface SimpleSelectProps {
  value: string;
  items: Record<string, string>;
  onValueChange: (value: string) => void;
  "aria-label"?: string;
  className?: string;
}

/** A select over a plain value-to-label map. */
export function SimpleSelect({
  value,
  items,
  onValueChange,
  className,
  ...rest
}: SimpleSelectProps) {
  return (
    <Select
      value={value}
      items={items}
      onValueChange={(next) => {
        if (next !== null) onValueChange(String(next));
      }}
    >
      <SelectTrigger className={cn("w-full", className)} aria-label={rest["aria-label"]}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(items).map(([key, label]) => (
          <SelectItem key={key} value={key}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
