from django.test import SimpleTestCase

from operation_control import assessment as A
from operation_control import csv_import as ci


class ScoringTests(SimpleTestCase):
    """Reference rows are the results your Excel ('برگه ارزیابی') calculated."""

    CASES = [
        # has_maker, type, maker, accuracy, environment, importance, wear, cost -> total, level, months
        (True, "PORTABLE", "ONE_YEAR", "HIGH", "MEDIUM", "HIGH", "HIGH", "VERY_HIGH", 40, 2, 12),      # LB124
        (True, "PORTABLE", "ONE_YEAR", "VERY_HIGH", "GOOD", "VERY_HIGH", "HIGH", "VERY_HIGH", 26, 2, 12),  # GR135
        (True, "PORTABLE", "ONE_YEAR", "MEDIUM", "VERY_GOOD", "HIGH", "MEDIUM", "HIGH", 57, 3, 24),    # SmartRad
        (True, "PORTABLE", "ONE_YEAR", "HIGH", "VERY_GOOD", "MEDIUM", "LOW", "VERY_HIGH", 70, 3, 24),  # LB6411
        (True, "PORTABLE", "ONE_YEAR", "MEDIUM", "GOOD", "HIGH", "LOW", "HIGH", 63, 3, 24),            # Inspector
    ]

    def test_matches_excel(self):
        for has, dt, mk, acc, env, imp, wear, cost, total, level, months in self.CASES:
            r = A.compute(has, dt, mk, acc, env, imp, wear, cost)
            self.assertEqual((r["total"], r["level"], r["months"]), (total, level, months))

    def test_without_manufacturer_uses_table_5_3(self):
        r = A.compute(False, "FIXED", None, "LOW", "VERY_GOOD", "LOW", "LOW", "VERY_HIGH")
        self.assertEqual((r["total"], r["level"], r["months"]), (100, 4, 36))     # 5+0+22+13+29+23+8
        self.assertEqual(r["scores"]["maker"], 0)
        self.assertIn(A.NO_MAKER_TEXT, r["justification"])

    def test_with_manufacturer_maximum_is_also_100(self):
        r = A.compute(True, "FIXED", "THREE_YEARS", "LOW", "VERY_GOOD", "LOW", "LOW", "VERY_HIGH")
        self.assertEqual(r["total"], 100)

    def test_level_boundaries(self):
        self.assertEqual([A.level_for(t)[1] for t in (0, 20, 21, 50, 51, 70, 71, 100)], [6, 6, 12, 12, 24, 24, 36, 36])

    def test_missing_or_invalid_answers_are_rejected(self):
        with self.assertRaises(ValueError):
            A.compute(True, "PORTABLE", None, "HIGH", "MEDIUM", "HIGH", "HIGH", "HIGH")      # maker missing
        with self.assertRaises(ValueError):
            A.compute(False, "PORTABLE", None, "NOPE", "MEDIUM", "HIGH", "HIGH", "HIGH")

    def test_justification_ends_with_the_total(self):
        r = A.compute(True, "PORTABLE", "ONE_YEAR", "HIGH", "MEDIUM", "HIGH", "HIGH", "VERY_HIGH")
        self.assertIn("امتیاز کل 40", r["justification"])
        self.assertIn("«یک ساله (۱۲ ماه)»", r["justification"])


class AssessmentImportTests(SimpleTestCase):
    def test_persian_sheet_headers_and_labels(self):
        text = ("نام / کد تجهیز حفاظت پرتوی,پیشنهاد سازنده موجود؟,نوع دستگاه,پیشنهاد کارخانه سازنده,دقت اندازه‌گیری / MSA,"
                "تاثیر شرایط محیطی,حوزه استفاده و اهمیت,فرسودگی / عوامل مخرب,هزینه کالیبراسیون,ملاحظات\n"
                "GR135,بله,قابل حمل,یک سال,خیلی‌زیاد,خوب,خیلی‌زیاد,زیاد,خیلی‌زیاد,\n"
                "LB124,بله,قابل حمل,یک سال,زیاد,متوسط,زیاد,زیاد,خیلی‌زیاد,نمونه تکمیل‌شده جهت راهنمایی\n"
                "RS230,بله,,,,,,,,\n")
        r = ci.parse_file("assessments", "a.csv", text.encode())
        self.assertEqual([i["ref"] for i in r["items"]], ["GR135"])
        item = r["items"][0]
        res = A.compute(item["has_maker"], item["device_type"], item["maker"], item["accuracy"],
                        item["environment"], item["importance"], item["wear"], item["cost"])
        self.assertEqual(res["total"], 26)
        self.assertEqual(len(r["errors"]), 1)                       # RS230: blank answers
        self.assertTrue(any("sample" in w[1] for w in r["warnings"]))   # the marked sample row is skipped

    def test_english_codes_and_inferred_manufacturer_flag(self):
        r = ci.parse_file("assessments", "a.csv",
                          b"equipment_id,device_type,maker_recommendation,accuracy,environment,importance,wear,cost\n"
                          b"PH-1,fixed,two_years,low,very_good,low,low,very_high\nPH-2,fixed,,low,very_good,low,low,very_high\n")
        self.assertEqual([(i["has_maker"], i["maker"]) for i in r["items"]], [(True, "TWO_YEARS"), (False, None)])

    def test_template_round_trips(self):
        r = ci.parse_file("assessments", "t.csv", ci.template_csv("assessments").encode("utf-8"))
        self.assertEqual(r["errors"], [])
        self.assertEqual(len(r["items"]), 2)
