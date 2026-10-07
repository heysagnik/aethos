import type { LinkComponentProps } from "@cloudflare/kumo";
import { forwardRef } from "react";
import { Link as RouterLink } from "react-router-dom";

const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;

/** Bridges Kumo's Link (and Sidebar items) to React Router. Backend and external URLs stay plain anchors. */
export const AppLink = forwardRef<HTMLAnchorElement, LinkComponentProps>(
  ({ href, to, ...rest }, ref) => {
    const target = href ?? to ?? "";
    if (EXTERNAL.test(target) || target.startsWith("/api/")) {
      return <a ref={ref} href={target} {...rest} />;
    }
    return <RouterLink ref={ref} to={target} {...rest} />;
  },
);
AppLink.displayName = "AppLink";
