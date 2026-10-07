import { useId, type ReactElement, cloneElement } from "react";
import { Label } from "@/components/ui/label";

interface FieldProps {
  label: string;
  description?: string;
  children: ReactElement<{ id?: string }>;
}

/** A label, optional hint and a control, wired together by id. */
export function Field({ label, description, children }: FieldProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {cloneElement(children, { id })}
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
    </div>
  );
}
