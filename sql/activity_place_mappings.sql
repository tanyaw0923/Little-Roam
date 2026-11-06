-- Optional, operator-reviewed links between curated venues and Google Place IDs.
-- Run this migration in Supabase SQL Editor. Do not insert IDs by guessing from names.
-- A Place ID must be matched to the actual venue/address manually before linking.
-- Place Details hours are looked up live and NEVER persisted in this table.
CREATE TABLE IF NOT EXISTS public.activity_place_mappings (
    source_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    google_place_id TEXT NOT NULL,
    verified_source_url TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_id, activity_id),
    FOREIGN KEY (source_id, activity_id)
      REFERENCES public.activities (source_id, activity_id)
      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS activity_place_mappings_id_idx
ON public.activity_place_mappings (google_place_id);

-- Example, only after human matching:
-- INSERT INTO public.activity_place_mappings
-- (source_id,activity_id,google_place_id,verified_source_url)
-- VALUES ('town_canmore_curated','elevation_place','VERIFIED_GOOGLE_PLACE_ID',
--         'https://www.canmore.ca/your-community/recreation')
-- ON CONFLICT (source_id,activity_id) DO UPDATE SET
-- google_place_id=EXCLUDED.google_place_id,
-- verified_source_url=EXCLUDED.verified_source_url,
-- verified_at=NOW();
