-- Little Roam reviewed official-hours seed: checked against the cited
-- official websites on 2026-11-06 (America/Edmonton). This is NOT a live scraper.
-- Apply AFTER sql/activity_official_hours.sql AND sql/seed_bow_valley.sql.
-- Expires 2026-11-20; rerunning does not artificially refresh verification.
-- Weekly descriptions refer to VENUE hours, not program/session bookings.
INSERT INTO public.activity_official_hours
(source_id,activity_id,weekly_hours,date_notices,source_url,verified_at,valid_until,notes)
VALUES
('town_banff_curated','fenlands',
 ARRAY[
 'Monday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Tuesday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Wednesday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Thursday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Friday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Saturday: 8:30 a.m. - 8:30 p.m. (closed public holidays)',
 'Sunday: 8:30 a.m. - 8:30 p.m. (closed public holidays)'
 ],
 '{}'::jsonb,
 'https://www.banff.ca/132/Fenlands-Banff-Recreation-Centre',
 '2026-11-06 00:00:00-07', '2026-11-20',
 'Town of Banff states closed on public holidays and facility hours may be extended for programs. Public skating schedules are separate.'),
('parks_canada_curated','cave_and_basin',
 ARRAY[
 'Monday: 11 a.m. - 5 p.m. (Oct 16 - May 14)',
 'Tuesday: Closed (Oct 16 - May 14)',
 'Wednesday: Closed (Oct 16 - May 14)',
 'Thursday: 11 a.m. - 5 p.m. (Oct 16 - May 14)',
 'Friday: 11 a.m. - 5 p.m. (Oct 16 - May 14)',
 'Saturday: 11 a.m. - 5 p.m. (Oct 16 - May 14)',
 'Sunday: 11 a.m. - 5 p.m. (Oct 16 - May 14)'
 ],
 '{"2026-12-14":"Parks Canada lists the site as closed December 14–17, 2026; recheck before visiting.",
   "2026-12-15":"Parks Canada lists the site as closed December 14–17, 2026; recheck before visiting.",
   "2026-12-16":"Parks Canada lists the site as closed December 14–17, 2026; recheck before visiting.",
   "2026-12-17":"Parks Canada lists the site as closed December 14–17, 2026; recheck before visiting.",
   "2026-12-25":"Parks Canada lists the site as closed on December 25; recheck before visiting."}'::jsonb,
 'https://parks.canada.ca/lhn-nhs/ab/caveandbasin/visit/heures-hours',
 '2026-11-06 00:00:00-07', '2026-11-20',
 'For October 16 through May 14 only; Parks Canada lists additional closures. Different summer schedule.')
ON CONFLICT(source_id,activity_id) DO UPDATE SET
 weekly_hours=EXCLUDED.weekly_hours,
 date_notices=EXCLUDED.date_notices,
 source_url=EXCLUDED.source_url,
 verified_at=EXCLUDED.verified_at,
 valid_until=EXCLUDED.valid_until,
 notes=EXCLUDED.notes;
