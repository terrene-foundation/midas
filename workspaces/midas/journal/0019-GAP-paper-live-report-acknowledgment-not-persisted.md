---
name: paper-live-report-acknowledgment-not-persisted
description: PaperToLiveFlow shows report acknowledgment UI but backend does not persist has_opened_report — frontend gate is cosmetic
type: GAP
---

# GAP: Paper→live "user opened report" not persisted to backend

## Finding

`specs/08-autonomy-and-trust.md` § Paper→Live Gate requires:

> "User has not opened the report and acknowledged"

The UI (`PaperLivePanel.tsx`) shows this as a blocking condition with `paperReportAcknowledged` and `ReviewSurface` requires scroll-to-bottom acknowledgment. However, no API endpoint persists this state to the database, and no backend enforcement checks it before allowing go-live.

```bash
$ grep -rn "report_acknowledged\|has_opened_report" src/midas/
# (empty — no backend persistence)
```

## Why it matters

A user could bypass the paper trading report review by refreshing the page or navigating away — the acknowledgment is client-side only. The spec's intent is that users must genuinely read the report before going live. Without backend enforcement, the gate can be circumvented.

## Fix required

1. Add `report_acknowledged_at: Optional[datetime]` and `report_acknowledged_by: str` fields to the `paper_live_state` model or a `user_settings` table
2. Add `POST /api/v1/settings/paper-live/acknowledge` endpoint that persists the acknowledgment with a timestamp
3. Add backend enforcement in the go-live transition: check `report_acknowledged_at IS NOT NULL` before allowing the transition
4. Wire the frontend `ReviewSurface` to call the acknowledge endpoint on scroll-to-bottom

## Spec reference

`specs/08-autonomy-and-trust.md` § Paper→Live Gate — blocking condition: "User has not opened the report and acknowledged"
