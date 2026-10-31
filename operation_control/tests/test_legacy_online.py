import datetime
from decimal import Decimal as D

from django.test import SimpleTestCase

from operation_control import csv_import as ci
from operation_control import legacy_online as O
from operation_control import legacy_tld as T

INDEX = T.build_worker_index([("1001", "علی اصغری"), ("1002", "رضا کریمی"), ("1003", "محمدرضا احمدی"), ("1004", "سارا نوری")])


def row(n, did, pid, date, dur, dose, place, name, first, last, center="مرکز تهران", address="خیابان آزادی"):
    return {"row": n, "ondoseid": did, "personnelid": pid, "datetime": date + " 00:00:00.0000000", "dureoftime": dur,
            "dose": dose, "placeid": place, "placename": name, "centername": center, "centeraddress": address,
            "firstname": first, "lastname": last, "pnumber": ""}


# the 7 rows of the screenshot
ROWS = [
    row(1, 1, 1, "1397-02-04", "01:04:00.0000000", "1.00", 1, "فیزیک بهداشت", "علی", "اصغری"),
    row(2, 2, 1, "1397-01-06", "10:00:00.0000000", "0.15", 1, "فیزیک بهداشت", "علی", "اصغری"),
    row(3, 4, 14, "1397-05-06", "01:45:00.0000000", "4.00", 7, "اتاق چشمه ها", "رضا", "کریمی"),
    row(4, 5, 20, "1397-05-06", "01:45:00.0000000", "1.00", 7, "اتاق چشمه ها", "محمدرضا", "احمدی"),
    row(5, 6, 12, "1397-05-06", "01:45:00.0000000", "5.00", 7, "اتاق چشمه ها", "سارا", "نوری"),
    row(6, 7, 12, "1397-05-01", "02:10:00.0000000", "7.00", 7, "اتاق چشمه ها", "سارا", "نوری"),
    row(7, 8, 20, "1397-05-01", "02:10:00.0000000", "8.00", 7, "اتاق چشمه ها", "محمدرضا", "احمدی"),
]


class DurationTests(SimpleTestCase):
    def test_durations(self):
        self.assertEqual(O.parse_duration("01:04:00.0000000"), 64)
        self.assertEqual(O.parse_duration("10:00:00"), 600)
        self.assertEqual(O.parse_duration("1:45"), 105)
        self.assertEqual(O.parse_duration(datetime.time(2, 10)), 130)
        self.assertEqual(O.parse_duration(datetime.timedelta(minutes=95)), 95)
        self.assertEqual(O.parse_duration("02:10:30"), 130)
        self.assertIsNone(O.parse_duration("00:00:00"))
        self.assertIsNone(O.parse_duration(None))
        with self.assertRaises(ValueError):
            O.parse_duration("soon")


class TransformTests(SimpleTestCase):
    def test_screenshot_rows_become_four_operations(self):
        r = O.transform(ROWS, INDEX)
        self.assertEqual(r["errors"], [])
        self.assertEqual(len(r["sessions"]), 4)
        by_day = {(s["date"], s["duration"]): s for s in r["sessions"]}
        three = by_day[(datetime.date(2018, 7, 28), 105)]                  # 1397-05-06, 01:45, three people
        self.assertEqual(sorted(ln["worker_code"] for ln in three["lines"]), ["1002", "1003", "1004"])
        self.assertEqual(three["place_name"], "اتاق چشمه ها")
        self.assertEqual(by_day[(datetime.date(2018, 7, 23), 130)]["lines"][1]["dose"], D("8.00"))   # 1397-05-01

    def test_mapping_of_place_centre_date_and_duration(self):
        s = O.transform(ROWS[:1], INDEX)["sessions"][0]
        self.assertEqual(s["place_name"], "فیزیک بهداشت")                  # place name = operation
        self.assertEqual(s["location"], "مرکز تهران — خیابان آزادی")        # centre name + address = location
        self.assertEqual(s["date"], datetime.date(2018, 4, 24))             # 1397-02-04
        self.assertEqual(s["duration"], 64)                                 # 01:04
        line = s["lines"][0]
        self.assertEqual((line["exposure"], line["legacy_ref"], line["unit"], line["dose_type"]), (64, "OnDoseID:1", "USV", "GAMMA"))

    def test_unit_is_a_parameter(self):
        self.assertEqual(O.transform(ROWS[:1], INDEX, unit="MSV")["sessions"][0]["lines"][0]["unit"], "MSV")

    def test_unknown_people_are_skipped_once_and_reported(self):
        stranger = [row(n, 20 + n, 99, "1397-05-01", "02:10:00", "2.00", 7, "اتاق چشمه ها", "شخص", "ناشناس") for n in (1, 2)]
        r = O.transform(ROWS[:1] + stranger, INDEX)
        self.assertEqual(len(r["sessions"]), 1)
        self.assertEqual(len(r["errors"]), 1)
        self.assertIn("2 dose(s) skipped", r["errors"][0][1])

    def test_bad_rows_do_not_stop_the_good_ones(self):
        bad = [row(1, 1, 1, "1397-02-45", "01:00:00", "1.0", 1, "x", "علی", "اصغری"),       # impossible date
               row(2, 2, 1, "1397-02-04", "01:00:00", "-1", 1, "x", "علی", "اصغری"),         # negative
               row(3, 3, 1, "1397-02-04", "01:00:00", "", 1, "x", "علی", "اصغری"),           # empty dose
               row(4, 4, 1, "1397-02-04", "01:00:00", "1.0", 1, "", "علی", "اصغری")]         # place has no name
        r = O.transform(bad + ROWS[:1], INDEX)
        self.assertEqual(len(r["sessions"]), 1)
        self.assertEqual((len(r["errors"]), len(r["warnings"])), (3, 1))

    def test_two_operations_on_one_day_at_one_place_stay_apart(self):
        rows = [row(1, 1, 1, "1397-05-06", "01:00:00", "1", 7, "اتاق چشمه ها", "علی", "اصغری"),
                row(2, 2, 1, "1397-05-06", "03:00:00", "2", 7, "اتاق چشمه ها", "علی", "اصغری")]
        self.assertEqual(len(O.transform(rows, INDEX)["sessions"]), 2)


class CsvEntryTests(SimpleTestCase):
    def test_ssms_csv_export_is_read(self):
        text = ("OnDoseID,PersonnelID,DateTime,DureofTime,Dose,PlaceID,PlaceName,CenterName,CenterAddress,firstName,LastName,PNumber\n"
                "1,1,1397-02-04,01:04:00,1.00,1,فیزیک بهداشت,NULL,NULL,علی,اصغری,\n")
        parsed = ci.parse_file("legacy_online", "online.csv", text.encode("utf-8-sig"))
        result = O.transform(parsed["items"], INDEX)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["sessions"][0]["location"], "")            # SQL NULLs do not become the text "NULL"

    def test_missing_columns_are_rejected(self):
        with self.assertRaises(ci.ImportFormatError):
            ci.parse_file("legacy_online", "x.csv", b"PersonnelID,Dose\n1,2\n")

    def test_template_round_trips(self):
        parsed = ci.parse_file("legacy_online", "t.csv", ci.template_csv("legacy_online").encode("utf-8"))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(len(parsed["items"]), 2)
