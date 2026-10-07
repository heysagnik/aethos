import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";

interface MeterBarProps {
  label: string;
  value: number;
  max?: number;
  valueText: string;
}

export function MeterBar({ label, value, max = 100, valueText }: MeterBarProps) {
  return (
    <Progress value={value} max={max}>
      <ProgressLabel>{label}</ProgressLabel>
      <ProgressValue>{() => valueText}</ProgressValue>
    </Progress>
  );
}
