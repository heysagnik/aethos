import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "body" | "secondary" | "heading" | "heading1" | "heading2" | "error" | "mono-secondary";
type Size = "xs" | "sm" | "base" | "lg";

const VARIANTS: Record<Variant, string> = {
  body: "text-foreground",
  secondary: "text-muted-foreground",
  heading: "font-semibold text-foreground",
  heading1: "text-4xl font-semibold tracking-tight text-foreground md:text-5xl",
  heading2: "text-2xl font-semibold text-foreground",
  error: "text-destructive",
  "mono-secondary": "font-mono text-muted-foreground",
};
const SIZES: Record<Size, string> = {
  xs: "text-xs",
  sm: "text-sm",
  base: "text-base",
  lg: "text-xl",
};

interface TextProps {
  variant?: Variant;
  size?: Size;
  as?: ElementType;
  bold?: boolean;
  truncate?: boolean;
  className?: string;
  id?: string;
  children: ReactNode;
}

export function Text({
  variant = "body",
  size = "base",
  as: Tag = "span",
  bold,
  truncate,
  className,
  ...rest
}: TextProps) {
  return (
    <Tag
      className={cn(
        SIZES[size],
        VARIANTS[variant],
        bold && "font-semibold",
        truncate && "truncate",
        className,
      )}
      {...rest}
    />
  );
}
