import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { LandingPage } from "../pages/LandingPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { Spinner } from "@/components/ui/spinner";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

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
      <Spinner className="size-6" />
    </div>
  );
}

/** Toggles the `dark` class from the operating system preference. */
function useColorMode(): void {
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.classList.toggle("dark", media.matches);
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
      <TooltipProvider>
        {children}
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/app" element={<AppShell />}>
          <Route path=":workspace" element={<OverviewPage />} />
          <Route path=":workspace/repos" element={<ReposPage />} />
          <Route path=":workspace/repos/:repoId" element={<RepoDetailPage />} />
          <Route path=":workspace/reviews" element={<ReviewsPage />} />
          <Route path=":workspace/reviews/:reviewId" element={<ReviewDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
