"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStatus } from "@/lib/queries/useOnboarding";
import { Skeleton } from "@/elements/LoadingSkeleton";

export function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data, isPending, isError } = useOnboardingStatus();

  useEffect(() => {
    if (isPending || isError) return;
    if (data && !data.activated) {
      router.replace("/onboarding");
    }
  }, [data, isPending, isError, router]);

  if (isPending) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-3 w-20" />
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>
    );
  }

  if (isError) {
    // Auth error or network failure — let the page render, auth middleware will handle
    return <>{children}</>;
  }

  if (data && !data.activated) {
    // Redirecting to onboarding — show nothing
    return null;
  }

  return <>{children}</>;
}
