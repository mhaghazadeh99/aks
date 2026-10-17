from decimal import Decimal

from django.test import SimpleTestCase

from operation_control import logic


class CellStateTests(SimpleTestCase):
    def test_states(self):
        # biweekly item: due in weeks 1, 3, 5 ...; today is week 5
        self.assertEqual(logic.cell_state(2, 1, True, 5), "done")
        self.assertEqual(logic.cell_state(2, 3, False, 5), "overdue")
        self.assertEqual(logic.cell_state(2, 5, False, 5), "current")
        self.assertEqual(logic.cell_state(2, 7, False, 5), "upcoming")
        self.assertEqual(logic.cell_state(2, 2, False, 5), "off")

    def test_done_wins_even_when_not_scheduled(self):
        self.assertEqual(logic.cell_state(4, 2, True, 5), "done")

    def test_current_week(self):
        self.assertEqual(logic.current_week(1405, 2, 1404, 5, 5), 0)      # before the plan year
        self.assertEqual(logic.current_week(1405, 2, 1405, 1, 20), 0)     # Farvardin, plan starts Ordibehesht
        self.assertEqual(logic.current_week(1405, 2, 1405, 7, 25), 24)    # 25 Mehr
        self.assertEqual(logic.current_week(1405, 2, 1406, 1, 1), 45)     # plan year is over

    def test_month_slot(self):
        self.assertEqual(logic.week_to_month_slot(1, 2), (2, 1))
        self.assertEqual(logic.week_to_month_slot(5, 2), (3, 1))
        self.assertEqual(logic.week_to_month_slot(44, 2), (12, 4))


class TLDPasteTests(SimpleTestCase):
    def test_excel_paste_with_header_and_persian_digits(self):
        text = ("TLD\tWorker\tPos\tGamma\tNeutron\n"
                "TL-001\t1001\tbody\t0.35\t0.02\n"
                "TL-002\tAli Rezaei\tدست\t۰٫۴۱\t-\n"
                "ENV-1\tGate\tenvironmental\t0,12\tND\tnear gate\n")
        rows, errors = logic.parse_tld_paste(text)
        self.assertEqual(errors, [])
        self.assertEqual([r["position"] for r in rows], ["BODY", "HAND", "ENV"])
        self.assertEqual(rows[1]["gamma"], Decimal("0.41"))
        self.assertIsNone(rows[1]["neutron"])
        self.assertEqual(rows[2]["gamma"], Decimal("0.12"))
        self.assertEqual(rows[2]["remarks"], "near gate")

    def test_errors_are_reported_per_line(self):
        rows, errors = logic.parse_tld_paste("TL-1,1001,body,abc,\nTL-2,1002,knee,0.1,\nTL-3,1003,body,,\n")
        self.assertEqual(rows, [])
        self.assertEqual([e[0] for e in errors], [1, 2, 3])

    def test_negative_dose_rejected(self):
        _rows, errors = logic.parse_tld_paste("TL-1,1001,body,-0.5,")
        self.assertEqual(len(errors), 1)
