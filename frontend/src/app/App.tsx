import { Loader, LinkProvider, Toasty } from "@cloudflare/kumo";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { AppLink } from "../components/AppLink";
import { LandingPage } from "../pages/LandingPage";
import { NotFoundPage } from "../pages/NotFoundPage";

// The dashboard is code-split so the landing page stays light.
const AppShell = lazy(() => import("./AppShell").then((m) => ({ default: m.AppShell })));
const OverviewPage = lazy(() =>
  import("../pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const ReposPage = lazy(() => import("../pages/ReposPage").then((m) => ({ default: m.ReposPage })));
const RepoDetailPage = lazy(() =>
  import("../pages/RepoDetailPage").then((m) => ({ default: m.RepoDetailPage })),
);
const ReviewsPage = lazy(() =>
  import("../pages/ReviewsPage").then((m) => ({ default: m.ReviewsPage })),
);
const ReviewDetailPage = lazy(() =>
  import("../pages/ReviewDetailPage").then((m) => ({ default: m.ReviewDetailPage })),
);

function PageFallback() {
  return (
    <div className="flex justify-center py-16" role="status" aria-label="Loading">
      <Loader size={24} />
    </div>
  );
}

/** Kumo reads `data-mode` for dark mode; follow the operating system preference. */
function useColorMode(): void {
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.mode = media.matches ? "dark" : "light";
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
  });
}

export function Providers({ children, client: given }: { children: ReactNode; client?: QueryClient }) {
  useColorMode();
  const [created] = useState(createQueryClient);
  const client = given ?? created;
  return (
    <QueryClientProvider client={client}>
      <LinkProvider component={AppLink}>
        <Toasty>{children}</Toasty>
      </LinkProvider>
    </QueryClientProvider>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="repos" element={<ReposPage />} />
          <Route path="repos/:repoId" element={<RepoDetailPage />} />
          <Route path="reviews" element={<ReviewsPage />} />
          <Route path="reviews/:reviewId" element={<ReviewDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
