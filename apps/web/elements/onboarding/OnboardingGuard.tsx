"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";

interface OnboardingStatus {
  activated: boolean;
  step: string;
}

export function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    api
      .get<OnboardingStatus>("/onboarding/status")
      .then((status) => {
        if (!status.activated) {
          router.replace("/onboarding");
        } else {
          setChecked(true);
        }
      })
      .catch(() => {
        // Auth error or network failure — let the page render, auth middleware will handle
        setChecked(true);
      });
  }, [router]);

  if (!checked) {
    return null;
  }

  return <>{children}</>;
}
