import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** A bordered panel for grouping content. */
export function Surface({ className, ...props }: ComponentProps<"div">) {
  return (
    <div className={cn("rounded-xl border bg-card text-card-foreground", className)} {...props} />
  );
}
