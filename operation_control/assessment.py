"""
Calibration-interval scoring (OIML D10 method) - a faithful port of the "برگه ارزیابی" and "جداول امتیازدهی"
sheets of your calibration workbook. Pure Python (no Django), tested against the 17 rows your Excel computed.

Seven factors, scored from tables 5-1 (with a manufacturer recommendation) or 5-3 (without one, MSA based);
the total (0-100) maps to a calibration level / interval through table 5-2.
"""

FACTORS = ["device_type", "maker", "accuracy", "environment", "importance", "wear", "cost"]

# score tables, generated from your workbook: fa label, en label, score with/without maker recommendation, audit text
TABLE = {
    "device_type": {
        "PORTABLE": {"fa": 'قابل حمل', "en": 'Portable', "with": 0, "without": 0, "why": 'دستگاه قابل\u200cحمل است و در معرض جابجایی، ضربه و تغییر شرایط محیطی بیشتری نسبت به دستگاه ثابت قرار می\u200cگیرد'},
        "FIXED": {"fa": 'غیر قابل حمل', "en": 'Fixed (non-portable)', "with": 5, "without": 5, "why": 'دستگاه ثابت (غیر قابل\u200cحمل) است و در شرایط پایدارتری نسبت به مدل\u200cهای قابل\u200cحمل نگهداری و استفاده می\u200cشود'},
    },
    "maker": {
        "SIX_MONTHS": {"fa": 'شش ماه', "en": 'Six months', "with": 0, "without": 0, "why": 'کارخانه سازنده با توجه به حساسیت بالای عملکرد دستگاه، کوتاه\u200cترین بازه پیشنهادی (شش ماه) را اعلام کرده است'},
        "ONE_YEAR": {"fa": 'یک سال', "en": 'One year', "with": 5, "without": 5, "why": 'کارخانه سازنده بازه یک\u200cساله را برای این تجهیز توصیه کرده است'},
        "TWO_YEARS": {"fa": 'دو سال', "en": 'Two years', "with": 8, "without": 8, "why": 'کارخانه سازنده با توجه به پایداری عملکرد دستگاه، بازه دو\u200cساله را توصیه کرده است'},
        "THREE_YEARS": {"fa": 'سه سال', "en": 'Three years', "with": 10, "without": 10, "why": 'کارخانه سازنده با توجه به پایداری بالای عملکرد دستگاه، طولانی\u200cترین بازه پیشنهادی (سه سال) را اعلام کرده است'},
    },
    "accuracy": {
        "LOW": {"fa": 'کم', "en": 'Low', "with": 20, "without": 22, "why": 'دقت اندازه\u200cگیری/نتایج MSA این تجهیز در سطح پایینی ارزیابی شده و نیازمند کنترل و کالیبراسیون مکرر\u200cتر است'},
        "MEDIUM": {"fa": 'متوسط', "en": 'Medium', "with": 15, "without": 17, "why": 'دقت اندازه\u200cگیری/نتایج MSA این تجهیز در سطح متوسط ارزیابی شده است'},
        "HIGH": {"fa": 'زیاد', "en": 'High', "with": 8, "without": 9, "why": 'دقت اندازه\u200cگیری/نتایج MSA این تجهیز بالا بوده و پایداری مناسب اندازه\u200cگیری را نشان می\u200cدهد'},
        "VERY_HIGH": {"fa": 'خیلی\u200cزیاد', "en": 'Very high', "with": 0, "without": 0, "why": 'دقت اندازه\u200cگیری/نتایج MSA این تجهیز بسیار بالا بوده و نیاز به کالیبراسیون مکرر را کاهش می\u200cدهد'},
    },
    "environment": {
        "VERY_GOOD": {"fa": 'خیلی خوب', "en": 'Very good', "with": 10, "without": 13, "why": 'دستگاه در شرایط محیطی کنترل\u200cشده و بسیار مناسب (دما، رطوبت و آلودگی در محدوده استاندارد) نگهداری و استفاده می\u200cشود'},
        "GOOD": {"fa": 'خوب', "en": 'Good', "with": 8, "without": 10, "why": 'دستگاه در شرایط محیطی مناسب نگهداری و استفاده می\u200cشود'},
        "MEDIUM": {"fa": 'متوسط', "en": 'Medium', "with": 4, "without": 5, "why": 'شرایط محیطی محل استقرار/استفاده دستگاه در حد متوسط ارزیابی شده است'},
        "BAD": {"fa": 'بد', "en": 'Bad', "with": 0, "without": 0, "why": 'دستگاه در معرض شرایط محیطی نامساعد (رطوبت، گرد و غبار، دمای نامناسب و ...) قرار دارد که می\u200cتواند بر عملکرد آن اثر بگذارد'},
    },
    "importance": {
        "VERY_HIGH": {"fa": 'خیلی\u200cزیاد', "en": 'Very high', "with": 0, "without": 0, "why": 'این تجهیز در کاربردی با اهمیت ایمنی/پرتویی بسیار بالا استفاده می\u200cشود که هرگونه خطای اندازه\u200cگیری آن می\u200cتواند پیامد جدی داشته باشد'},
        "HIGH": {"fa": 'زیاد', "en": 'High', "with": 10, "without": 10, "why": 'این تجهیز در کاربردی با اهمیت بالا در حفاظت پرتوی مورد استفاده قرار می\u200cگیرد'},
        "MEDIUM": {"fa": 'متوسط', "en": 'Medium', "with": 19, "without": 20, "why": 'اهمیت کاربرد این تجهیز نسبت به سایر تجهیزات حفاظت پرتوی در سطح متوسط ارزیابی شده است'},
        "LOW": {"fa": 'پایین', "en": 'Low', "with": 27, "without": 29, "why": 'اهمیت کاربرد این تجهیز نسبت به سایر تجهیزات حفاظت پرتوی کمتر است'},
    },
    "wear": {
        "VERY_HIGH": {"fa": 'خیلی\u200cزیاد', "en": 'Very high', "with": 0, "without": 0, "why": 'دستگاه فرسودگی بالایی دارد و در طول عمر خود به\u200cطور مکرر در معرض عوامل مخرب (ضربه، رطوبت، آلودگی و ...) بوده است'},
        "HIGH": {"fa": 'زیاد', "en": 'High', "with": 5, "without": 6, "why": 'دستگاه فرسودگی نسبتاً بالایی دارد'},
        "MEDIUM": {"fa": 'متوسط', "en": 'Medium', "with": 12, "without": 14, "why": 'میزان فرسودگی دستگاه در حد متوسط است'},
        "LOW": {"fa": 'پایین', "en": 'Low', "with": 20, "without": 23, "why": 'دستگاه فرسودگی کمی دارد و کمتر در معرض عوامل مخرب بوده است'},
    },
    "cost": {
        "VERY_HIGH": {"fa": 'خیلی\u200cزیاد', "en": 'Very high', "with": 8, "without": 8, "why": 'با توجه به هزینه بسیار بالای کالیبراسیون این تجهیز، افزایش بازه کالیبراسیون از نظر اقتصادی توجیه\u200cپذیر است'},
        "HIGH": {"fa": 'زیاد', "en": 'High', "with": 5, "without": 5, "why": 'هزینه کالیبراسیون این تجهیز نسبتاً بالاست'},
        "MEDIUM": {"fa": 'متوسط', "en": 'Medium', "with": 2, "without": 2, "why": 'هزینه کالیبراسیون این تجهیز در سطح متوسط است'},
        "LOW": {"fa": 'کم', "en": 'Low', "with": 0, "without": 0, "why": 'هزینه کالیبراسیون این تجهیز پایین است و کالیبراسیون مکرر\u200cتر توجیه اقتصادی دارد'},
    },
}

# table 5-2: (minimum total, level, interval in months)
LEVELS = [(71, 4, 36), (51, 3, 24), (21, 2, 12), (0, 1, 6)]
LEVEL_LABEL_FA = {36: "سه ساله (۳۶ ماه)", 24: "دو ساله (۲۴ ماه)", 12: "یک ساله (۱۲ ماه)", 6: "شش ماهه (۶ ماه)"}
NO_MAKER_TEXT = "پیشنهاد کارخانه سازنده برای این تجهیز موجود نبوده و امتیازدهی بر مبنای نتایج MSA انجام شده است"


def choices(factor):
    """[(code, english label)] in table order - used to build model choices / form selects."""
    return [(code, row["en"]) for code, row in TABLE[factor].items()]


def level_for(total):
    for minimum, level, months in LEVELS:
        if total >= minimum:
            return level, months
    return 1, 6


def compute(has_maker, device_type, maker, accuracy, environment, importance, wear, cost):
    """
    Returns {"scores": {factor: points}, "total", "level", "months", "justification"}.
    Raises ValueError when an answer is missing/invalid (maker is only needed when has_maker is true).
    """
    answers = {"device_type": device_type, "maker": maker if has_maker else None, "accuracy": accuracy,
               "environment": environment, "importance": importance, "wear": wear, "cost": cost}
    scores, reasons = {}, []
    for factor in FACTORS:
        code = answers[factor]
        if factor == "maker" and not has_maker:
            scores[factor] = 0
            reasons.append(NO_MAKER_TEXT)
            continue
        row = TABLE[factor].get(code)
        if row is None:
            raise ValueError(f"{factor}: invalid or missing answer {code!r}")
        scores[factor] = row["with" if has_maker else "without"]
        reasons.append(row["why"])
    total = sum(scores.values())
    level, months = level_for(total)
    reasons.append(
        f"در مجموع امتیاز کل {total} از ۱۰۰ محاسبه شد که بر اساس جدول ۵-۲ روش اجرایی معادل سطح {level} "
        f"و بازه کالیبراسیون «{LEVEL_LABEL_FA[months]}» برای این تجهیز است.")
    return {"scores": scores, "total": total, "level": level, "months": months,
            "justification": "؛ ".join(reasons)}


def js_table():
    """Compact {factor: {code: [with, without]}} for the live preview in the form."""
    return {f: {c: [r["with"], r["without"]] for c, r in rows.items()} for f, rows in TABLE.items()}
