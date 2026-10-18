import datetime
from decimal import Decimal

from django.test import SimpleTestCase

from operation_control import csv_import as ci


def parse(kind, text, name="x.csv", encoding="utf-8"):
    return ci.parse_file(kind, name, text.encode(encoding))


class EquipmentImportTests(SimpleTestCase):
    def test_persian_headers_dates_status_and_period_text(self):
        text = ("نام دستگاه,شماره شناسایی تجهیز,وضعیت دستگاه,مرکز نگهداری,دوره کالیبراسیون (ماه),تاریخ آخرین کالیبراسیون (شمسی),شماره گواهی کالیبراسیون\n"
                "GR-135,PH-0001,فعال,تهران,12,1402/09/15,0209\n"
                "SmartRad,PH-0007,امانت به آقای امینی,تهران,بعد تعویض گاز,,\n"
                "No id,,فعال,,12,,\n")
        r = parse("equipment", text)
        a, b = r["items"]
        self.assertEqual(a["fields"]["status"], "ACTIVE")
        self.assertEqual(a["fields"]["center"], "TEHRAN")
        self.assertEqual(a["calibration"]["date"], datetime.date(2023, 12, 6))
        self.assertEqual(b["fields"]["status"], "LOAN")
        self.assertEqual(b["fields"]["loan_to"], "آقای امینی")
        self.assertEqual(b["fields"]["calibration_period_months"], 12)
        self.assertIn("بعد تعویض گاز", b["fields"]["notes"])
        self.assertEqual(len(r["errors"]), 1)                       # the row without an ID

    def test_unrecognised_file(self):
        with self.assertRaises(ci.ImportFormatError):
            parse("equipment", "foo,bar\n1,2\n")

    def test_missing_required_column(self):
        with self.assertRaises(ci.ImportFormatError):
            parse("equipment", "equipment_id,model_name\nA,B\n")

    def test_legacy_windows_1256_csv(self):
        text = "کد پرسنلی;نام و نام خانوادگی\n111;علی اصغری\n".replace("ی", "ي").replace("ک", "ك")
        r = parse("workers", text, encoding="cp1256")
        self.assertEqual(r["items"][0]["fields"]["full_name"], "علی اصغری")   # Arabic letters normalised back to Persian


class WorkerImportTests(SimpleTestCase):
    def test_status_and_exit_date(self):
        r = parse("workers", "personnel_code,full_name,status,exit_date\n1,A,فعال,\n2,B,غیرفعال,1405/03/10\n,,,1405/01/01\n3,,,\n")
        self.assertEqual([i["fields"]["status"] for i in r["items"]], ["ACTIVE", "LEFT"])
        self.assertEqual(r["items"][1]["fields"]["exit_date"], datetime.date(2026, 5, 31))
        self.assertEqual(len(r["errors"]), 1)                       # row 5: code without name; stray date-only row ignored


class TLDImportTests(SimpleTestCase):
    HEAD = "سال شمسی دوره,فصل دوره,تاریخ ثبت گزارش (شمسی),شماره گزارش دریافتی,کد TLD,کد پرسنلی (شماره فرد),نام و نام خانوادگی,مقدار دز,واحد\n"

    def test_legacy_registry_rows(self):
        r = parse("tld", self.HEAD +
                  "1404,بهار,1405/04/21,TL6289,T1,111,A,350,µSv\n"
                  "1404,بهار,1405/04/21,TL6289,T2,222,B,0.41,mSv\n"
                  "1404,بهار,1405/04/21,TL6289,,,,,\n"            # pre-filled template row: ignored
                  "1404,بهار,1405/04/21,TL6289,,222,B,0.1,mSv\n"   # no TLD code: error
                  "1404,بهار,1405/04/21,TL6289,T4,222,B,abc,mSv\n")
        self.assertEqual([i["tld_code"] for i in r["items"]], ["T1", "T2"])
        self.assertEqual(r["items"][0]["gamma"], Decimal("0.350"))     # µSv -> mSv
        self.assertEqual(r["items"][0]["season"], 1)
        self.assertEqual(len(r["errors"]), 2)
        self.assertTrue(any("gamma" in w[1] for w in r["warnings"]))

    def test_gamma_neutron_env_and_hand(self):
        r = parse("tld", "year,season,tld_code,personnel_code,full_name,env_point,position,gamma_msv,neutron_msv\n"
                         "1404,Spring,T1,111,A,,body,0.3,0.02\n1404,Spring,T2,111,A,,hand,1.2,\n1404,Spring,E1,,,Gate,environmental,0.1,ND\n"
                         "1404,Spring,E2,,,,environmental,0.1,\n")
        self.assertEqual([i["position"] for i in r["items"]], ["BODY", "HAND", "ENV"])
        self.assertIsNone(r["items"][1]["neutron"])
        self.assertEqual(len(r["errors"]), 1)                          # environmental row without a point


class OnlineDoseImportTests(SimpleTestCase):
    def test_units_types_and_errors(self):
        r = parse("online_doses",
                  "date,operation,location,personnel_code,device,dose_type,dose_value,unit,exposure_minutes\n"
                  "1405/07/20,Conditioning,Hall,1,PH-1,gamma,35,uSv,60\n"
                  "1405/07/20,Conditioning,Hall,2,PH-2,نوترون,0.004,mSv,\n"
                  "1405/07/20,Conditioning,Hall,3,PH-3,x-ray,1,uSv,\n"
                  "1405/07/21,Sampling,,3,PH-1,gamma,5,,\n")
        self.assertEqual([(i["dose_type"], i["unit"]) for i in r["items"]],
                         [("GAMMA", "USV"), ("NEUTRON", "MSV"), ("GAMMA", "USV")])   # blank unit = uSv
        self.assertEqual(len(r["errors"]), 1)


class InspectionImportTests(SimpleTestCase):
    def test_period_words_blank_title_and_weeks(self):
        r = parse("inspection", "title,form_code,area,period,is_active,done_weeks\n"
                                "Env dose,S4-1,Tehran,Every two weeks,yes,\"1,3,5\"\n"
                                ",S4-2,Karaj,ماهانه,no,1-3\n"
                                "Bad,,Area,fortnightly,,\n")
        a, b = r["items"]
        self.assertEqual((a["fields"]["period_weeks"], a["done_weeks"]), (2, [1, 3, 5]))
        self.assertEqual((b["title"], b["fields"]["period_weeks"], b["fields"]["is_active"], b["done_weeks"]), ("Env dose", 4, False, [1, 2, 3]))
        self.assertEqual(len(r["errors"]), 1)


class TemplateTests(SimpleTestCase):
    def test_every_template_imports_cleanly(self):
        for kind in ci.TEMPLATES:
            r = ci.parse_file(kind, "t.csv", ci.template_csv(kind).encode("utf-8"))
            self.assertEqual(r["errors"], [], kind)
            self.assertTrue(r["items"], kind)

    def test_dates(self):
        self.assertEqual(ci.parse_date("۱۴۰۵/۰۷/۲۵"), datetime.date(2026, 10, 17))
        self.assertEqual(ci.parse_date("2026-10-17"), datetime.date(2026, 10, 17))
        self.assertIsNone(ci.parse_date(""))
        with self.assertRaises(ValueError):
            ci.parse_date("1404/12/30")
