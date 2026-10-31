import datetime
from decimal import Decimal as D

from django.test import SimpleTestCase

from operation_control import csv_import as ci
from operation_control import legacy_tld as L

WORKERS = [("1001", "علی اصغری"), ("1002", "رضا کریمی"), ("1003", "محمدرضا احمدی"), ("1004", "سارا نوری"), ("1005", "سارا نوری")]
INDEX = L.build_worker_index(WORKERS)


def row(n, pid, dose, value, date_id, first, last, d1="1396-09-14", d2="1396-11-21", number="EPL/TLD/96/007", pnumber=""):
    return {"row": n, "tldid": n + 20, "personnelid": pid, "doseid": dose, "measured": value, "uncertinty": "18",
            "dateid": date_id, "descriptions": None, "jobtype": None, "date1": d1, "date2": d2,
            "numberoftest": number, "labid": 2, "firstname": first, "lastname": last, "pnumber": pnumber}


class SeasonRuleTests(SimpleTestCase):
    """The 8 DateD rows from the screenshot, using the 'middle of the period' rule."""

    CASES = [
        ("1396-09-14", "1396-11-21", 1396, 4), ("1396-11-21", "1397-02-15", 1397, 1),
        ("1396-05-29", "1396-09-26", 1396, 3), ("1396-01-27", "1396-05-28", 1396, 1),
        ("1395-12-25", "1396-03-01", 1396, 1), ("1395-08-28", "1395-12-25", 1395, 4),
        ("1397-02-15", "1397-06-11", 1397, 2), ("1397-06-11", "1397-08-15", 1397, 3),
    ]

    def test_middle_of_the_period(self):
        for d1, d2, year, season in self.CASES:
            self.assertEqual(L.period_season(d1, d2)[:2], (year, season), (d1, d2))

    def test_database_dates_are_jalali_numbers_in_a_date_column(self):
        self.assertEqual(L.to_jalali_ymd(datetime.datetime(1396, 9, 14)), (1396, 9, 14))
        self.assertEqual(L.to_jalali_ymd("1396-09-14 00:00:00.0000000"), (1396, 9, 14))
        self.assertEqual(L.to_jalali_ymd("۱۳۹۶/۰۹/۱۴"), (1396, 9, 14))
        self.assertEqual(L.to_jalali_ymd(datetime.date(2026, 10, 17)), (1405, 7, 25))   # a real Gregorian date is converted
        with self.assertRaises(ValueError):
            L.to_jalali_ymd("1396-02-45")

    def test_reversed_period_is_swapped(self):
        y, s, start, end, swapped = L.period_season("1396-11-21", "1396-09-14")
        self.assertTrue(swapped)
        self.assertLess(start, end)


class MatchingTests(SimpleTestCase):
    def test_names_ignore_spacing_and_arabic_letters(self):
        self.assertEqual(L.match_person(INDEX, "علي", "اصغري"), ("worker", "1001"))
        self.assertEqual(L.match_person(INDEX, "محمد رضا", "احمدی"), ("worker", "1003"))
        self.assertEqual(L.match_person(INDEX, "اصغری", "علی"), ("worker", "1001"))        # last + first order

    def test_personnel_number_is_the_fallback(self):
        self.assertEqual(L.match_person(INDEX, "", "", "1002"), ("worker", "1002"))

    def test_ambiguous_and_unknown(self):
        self.assertEqual(L.match_person(INDEX, "سارا", "نوری")[0], "ambiguous")
        self.assertEqual(L.match_person(INDEX, "محل", "دروازه")[0], "none")


class TransformTests(SimpleTestCase):
    def test_doses_are_merged_into_one_body_reading_and_one_hand_reading(self):
        rows = [row(1, 10, 4, "0.050", 14, "رضا", "کریمی"), row(2, 10, 10, "0.020", 14, "رضا", "کریمی"),
                row(3, 10, 3, "0.070", 14, "رضا", "کریمی"), row(4, 10, 5, "0.900", 14, "رضا", "کریمی")]
        r = L.transform(rows, INDEX)
        body, hand = r["readings"]
        self.assertEqual((body["position"], body["gamma"], body["neutron"]), ("BODY", D("0.050"), D("0.020")))
        self.assertEqual((hand["position"], hand["gamma"], hand["neutron"]), ("HAND", D("0.900"), None))
        self.assertEqual(r["warnings"], [])                       # photon + neutron == total
        self.assertEqual(body["tld_code"], "L14-10-B")

    def test_total_only_is_imported_as_gamma_and_remarked(self):
        r = L.transform([row(1, 8, 3, "0.060", 14, "علی", "اصغری")], INDEX)
        rd = r["readings"][0]
        self.assertEqual((rd["gamma"], rd["neutron"]), (D("0.060"), None))
        self.assertIn("only the total effective dose", rd["remarks"])
        self.assertIn("uncertainty: 18", rd["remarks"])

    def test_inconsistent_total_is_reported(self):
        r = L.transform([row(1, 10, 4, "0.200", 14, "رضا", "کریمی"), row(2, 10, 3, "0.500", 14, "رضا", "کریمی")], INDEX)
        self.assertEqual(r["readings"][0]["gamma"], D("0.200"))   # the components win over the total
        self.assertTrue(any("differs from the recorded total" in w[1] for w in r["warnings"]))

    def test_case_studies_become_environmental_points(self):
        rows = [row(1, 5, 3, "0.020", 14, "محل", "دروازه اصلی")]
        r = L.transform(rows, INDEX)
        self.assertEqual((r["readings"][0]["position"], r["readings"][0]["kind"]), ("ENV", "env"))
        self.assertEqual(r["env_names"], ["محل دروازه اصلی"])
        self.assertEqual(L.transform(rows, INDEX, unmatched="skip")["readings"], [])

    def test_ambiguous_names_are_skipped_with_an_error(self):
        r = L.transform([row(1, 13, 3, "0.030", 14, "سارا", "نوری")], INDEX)
        self.assertEqual(r["readings"], [])
        self.assertEqual(len(r["errors"]), 1)

    def test_two_lab_reports_in_one_season_stay_separate(self):
        rows = [row(1, 8, 3, "0.040", 31, "علی", "اصغری", d1="1395-12-25", d2="1396-03-01", number="EPL/TLD/96/002"),
                row(2, 8, 3, "0.045", 30, "علی", "اصغری", d1="1396-01-27", d2="1396-05-28", number="EPL/TLD/96/003")]
        r = L.transform(rows, INDEX)
        self.assertEqual({(v["year"], v["season"], v["report_number"]) for v in r["reports"].values()},
                         {(1396, 1, "EPL/TLD/96/002"), (1396, 1, "EPL/TLD/96/003")})
        self.assertTrue(any("2 lab reports" in w[1] for w in r["warnings"]))

    def test_bad_rows_do_not_stop_the_good_ones(self):
        rows = [row(1, 8, 3, "abc", 20, "علی", "اصغری", d1="1396-11-21", d2="1397-02-15"),      # bad number
                row(2, 8, 3, "0.1", 40, "علی", "اصغری", d1="1396-02-45", d2="1396-05-28"),     # impossible date
                row(3, 8, 99, "1", 14, "علی", "اصغری"),                                         # unknown DoseID
                row(4, 8, 3, "", 14, "علی", "اصغری"),                                           # empty value
                row(5, 8, 4, "0.01", 14, "علی", "اصغری")]
        r = L.transform(rows, INDEX)
        self.assertEqual(len(r["readings"]), 1)
        self.assertEqual(len(r["errors"]), 2)
        self.assertEqual(len(r["warnings"]), 2)

    def test_one_worker_under_two_personnel_ids_is_flagged(self):
        r = L.transform([row(1, 8, 3, "0.060", 14, "علی", "اصغری"), row(2, 11, 3, "0.110", 14, "علي", "اصغري")], INDEX)
        self.assertTrue(any("several PersonnelIDs" in w[1] for w in r["warnings"]))


class CsvEntryTests(SimpleTestCase):
    def test_ssms_csv_export_is_read(self):
        text = ("TLDID,PersonnelID,DoseID,MeasureD,Uncertinty,DateID,Descriptions,JobType,Date1,Date2,NumberofTest,LabID,firstName,LastName,PNumber\n"
                "21,8,3,0.060,18,14,NULL,NULL,1396-09-14,1396-11-21,EPL/TLD/96/007,2,علی,اصغری,\n")
        parsed = ci.parse_file("legacy_tld", "tld.csv", text.encode("utf-8-sig"))
        self.assertEqual(len(parsed["items"]), 1)
        result = L.transform(parsed["items"], INDEX)
        self.assertEqual(result["readings"][0]["worker_code"], "1001")
        self.assertEqual(result["readings"][0]["remarks"].count("NULL"), 0)             # SQL NULLs are not copied into remarks

    def test_missing_columns_are_rejected(self):
        with self.assertRaises(ci.ImportFormatError):
            ci.parse_file("legacy_tld", "x.csv", b"PersonnelID,MeasureD\n1,0.1\n")

    def test_template_round_trips(self):
        parsed = ci.parse_file("legacy_tld", "t.csv", ci.template_csv("legacy_tld").encode("utf-8"))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(len(parsed["items"]), 2)
