import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { AttentionReport, NotificationPreferences } from "@/lib/types";

export const NOTIF_KEY = ["notification-preferences"];

export function useNotificationPreferences() {
  return useQuery<NotificationPreferences>({
    queryKey: NOTIF_KEY,
    queryFn: () => api.get("/settings/notifications/preferences"),
    staleTime: 60_000,
  });
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (prefs: Partial<NotificationPreferences>) =>
      api.put("/settings/notifications/preferences", prefs),
    onSuccess: () => qc.invalidateQueries({ queryKey: NOTIF_KEY }),
  });
}

export function useAttentionReport() {
  return useQuery<AttentionReport>({
    queryKey: ["attention-report"],
    queryFn: () => api.get("/settings/notifications/attention-report"),
    staleTime: 60_000,
  });
}
