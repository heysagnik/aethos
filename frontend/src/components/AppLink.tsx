import type { VariantProps } from "class-variance-authority";
import { forwardRef, type AnchorHTMLAttributes } from "react";
import { Link as RouterLink } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;

interface AppLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  href: string;
  external?: boolean;
}

/** Routes in-app paths through React Router. Backend and external URLs stay plain anchors. */
export const AppLink = forwardRef<HTMLAnchorElement, AppLinkProps>(
  ({ href, external, ...rest }, ref) => {
    if (external || EXTERNAL.test(href) || href.startsWith("/api/")) {
      return (
        <a
          ref={ref}
          href={href}
          {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
          {...rest}
        />
      );
    }
    return <RouterLink ref={ref} to={href} {...rest} />;
  },
);
AppLink.displayName = "AppLink";

/** Inline text link. */
export const TextLink = forwardRef<HTMLAnchorElement, AppLinkProps>(
  ({ className, ...props }, ref) => (
    <AppLink
      ref={ref}
      className={cn("font-medium text-foreground underline-offset-4 hover:underline", className)}
      {...props}
    />
  ),
);
TextLink.displayName = "TextLink";

type LinkButtonProps = AppLinkProps & VariantProps<typeof buttonVariants>;

/** A link that looks like a button. */
export const LinkButton = forwardRef<HTMLAnchorElement, LinkButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <AppLink ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
LinkButton.displayName = "LinkButton";
