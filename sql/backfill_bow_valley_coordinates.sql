-- Regional search requires coordinates. Add approximate mapped venue/park
-- coordinates to the six explicitly curated Bow Valley records.
-- Coordinates transcribed from OpenStreetMap-derived Mapcarta place pages
-- (attribution: © OpenStreetMap contributors; https://www.openstreetmap.org/copyright).
-- Verify entrances and routing independently before user-facing navigation.
-- These are representative points, not guaranteed site entrances.
-- Re-running is idempotent. Does not modify Calgary Open Data records.
WITH mapped(source_id,activity_id,lat,lon) AS (
 VALUES
 ('town_canmore_curated','elevation_place',51.08886::float8,-115.35048::float8),
 ('town_canmore_curated','quarry_lake',51.07541,-115.37260),
 ('town_canmore_curated','riverside_park',51.08771,-115.36541),
 ('town_banff_curated','fenlands',51.18305,-115.57859),
 ('town_banff_curated','recreation_grounds',51.17307,-115.57629),
 ('town_banff_curated','central_park',51.17366,-115.57284)
)
UPDATE public.activities AS a
SET latitude = m.lat, longitude = m.lon, updated_at = NOW()
FROM mapped AS m
WHERE a.source_id=m.source_id AND a.activity_id=m.activity_id
  AND (a.latitude IS DISTINCT FROM m.lat OR a.longitude IS DISTINCT FROM m.lon);
