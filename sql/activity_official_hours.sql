-- Little Roam: operator-reviewed, independently sourced official venue hours.
-- Google Places hours must NOT be copied into this table.
-- Populate ONLY after reviewing the named venue's official page or licensed feed.
CREATE TABLE IF NOT EXISTS public.activity_official_hours (
    source_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    weekly_hours TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Explicit dated notices are displayed as notices, NOT automatic open/closed proof.
    date_notices JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_url TEXT NOT NULL CHECK (source_url ~ '^https://'),
    verified_at TIMESTAMPTZ NOT NULL,
    valid_until DATE NOT NULL,
    notes TEXT,
    PRIMARY KEY(source_id, activity_id),
    FOREIGN KEY(source_id, activity_id)
      REFERENCES public.activities(source_id, activity_id) ON DELETE CASCADE,
    CHECK (valid_until >= (verified_at AT TIME ZONE 'America/Edmonton')::date),
    CHECK (jsonb_typeof(date_notices) = 'object'),
    CHECK (array_length(weekly_hours, 1) IS NULL OR array_length(weekly_hours, 1) <= 7)
);
CREATE INDEX IF NOT EXISTS activity_official_hours_valid_until_idx
  ON public.activity_official_hours(valid_until);

-- Example of the REVIEW WORKFLOW ONLY (not actual verified hours):
-- After checking the official venue page, supply the real weekday descriptions,
-- verified time, source URL and a conservative expiration date.
-- INSERT INTO public.activity_official_hours
-- (source_id, activity_id, weekly_hours, date_notices, source_url, verified_at, valid_until)
-- VALUES ('town_canmore_curated', 'elevation_place',
--  ARRAY['Monday: [hours confirmed from official source]'],
--  '{}'::jsonb, 'https://example.invalid/REPLACE-WITH-OFFICIAL-SOURCE',
--  NOW(), CURRENT_DATE + 7)
-- ON CONFLICT (source_id, activity_id) DO UPDATE SET
-- weekly_hours=EXCLUDED.weekly_hours,
-- date_notices=EXCLUDED.date_notices,
-- source_url=EXCLUDED.source_url,
-- verified_at=EXCLUDED.verified_at,
-- valid_until=EXCLUDED.valid_until;
