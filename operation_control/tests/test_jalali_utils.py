import datetime

from django.test import SimpleTestCase

from operation_control import jalali_utils as ju

D = datetime.date


class JalaliUtilsTests(SimpleTestCase):
    def test_known_conversions(self):
        for g, j in [(D(2026, 3, 21), (1405, 1, 1)), (D(2025, 3, 21), (1404, 1, 1)),
                     (D(2024, 3, 20), (1403, 1, 1)), (D(1979, 2, 11), (1357, 11, 22)),
                     (D(2026, 10, 17), (1405, 7, 25)), (D(2025, 3, 20), (1403, 12, 30))]:
            self.assertEqual(ju.to_jalali(g), j)
            self.assertEqual(ju.from_jalali(*j), g)

    def test_round_trip_and_no_gaps(self):
        prev = None
        for jy in range(1380, 1430):
            for jm in range(1, 13):
                for jd in range(1, ju.days_in_month(jy, jm) + 1):
                    g = ju.from_jalali(jy, jm, jd)
                    self.assertEqual(ju.to_jalali(g), (jy, jm, jd))
                    if prev:
                        self.assertEqual((g - prev).days, 1)
                    prev = g

    def test_leap_years(self):
        self.assertTrue(ju.is_leap(1399))
        self.assertTrue(ju.is_leap(1403))
        self.assertFalse(ju.is_leap(1404))

    def test_add_months_is_jalali_aware(self):
        self.assertEqual(ju.add_months(D(2023, 12, 6), 12), D(2024, 12, 5))        # 1402/09/15 -> 1403/09/15
        self.assertEqual(ju.add_months_ymd(1405, 4, 24, 24), (1407, 4, 24))
        self.assertEqual(ju.add_months_ymd(1404, 8, 31, 1), (1404, 9, 30))
        self.assertEqual(ju.add_months_ymd(1403, 12, 30, 12), (1404, 12, 29))
        self.assertIsNone(ju.add_months(None, 12))

    def test_plan_week_matches_excel(self):
        self.assertEqual(ju.plan_week_ymd(1, 10), 0)
        self.assertEqual(ju.plan_week_ymd(2, 1), 1)
        self.assertEqual(ju.plan_week_ymd(2, 22), 4)
        self.assertEqual(ju.plan_week_ymd(12, 30), 44)

    def test_season(self):
        self.assertEqual([ju.season_of_month(m) for m in (1, 3, 4, 6, 7, 10, 12)], [1, 1, 2, 2, 3, 4, 4])
        self.assertEqual(ju.season_of_date(D(2026, 10, 17)), 3)   # Mehr -> autumn

    def test_parse_and_format(self):
        self.assertEqual(ju.parse_jalali_str("1405/04/24"), (1405, 4, 24))
        self.assertIsNone(ju.parse_jalali_str("1405/13/01"))
        self.assertIsNone(ju.parse_jalali_str("1404/12/30"))
        self.assertEqual(ju.fmt(D(2026, 10, 17)), "1405/07/25")
        self.assertEqual(ju.fmt(None), "")
