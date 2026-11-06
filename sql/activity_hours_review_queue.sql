-- One-time migration. This is a *review queue*, not the public verified-hours table.
-- Rows are independently obtained from approved official venue websites only.
-- Google Places hours and search content must never be stored here.
CREATE TABLE IF NOT EXISTS public.activity_hours_review_queue (
    source_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    discovered_hours TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    source_url TEXT,
    discovery_status TEXT NOT NULL
      CHECK (discovery_status IN ('pending_review','no_structured_hours','fetch_failed')),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewer_note TEXT,
    PRIMARY KEY(source_id, activity_id),
    FOREIGN KEY(source_id,activity_id)
      REFERENCES public.activities(source_id,activity_id) ON DELETE CASCADE
);
-- Only review the source URL and discovered-hours lines; manually validate
-- venue identity, seasonal schedules, public holidays and programme-specific hours.
-- The approval CLI promotes an inspected pending row to activity_official_hours.
CREATE INDEX IF NOT EXISTS activity_hours_review_queue_status_idx
 ON public.activity_hours_review_queue(discovery_status, discovered_at);
