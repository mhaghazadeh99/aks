import re


LETTER_NUMBER = re.compile(
    r"(شماره|شماره نامه)\s*[:：]?\s*([^\n]+)"
)

LETTER_DATE = re.compile(
    r"(تاریخ)\s*[:：]?\s*([^\n]+)"
)


def parse_text(text):

    data = {

        "letter_number": "",

        "letter_date": "",

        "sources": [],

    }

    m = LETTER_NUMBER.search(text)

    if m:

        data["letter_number"] = m.group(2).strip()

    m = LETTER_DATE.search(text)

    if m:

        data["letter_date"] = m.group(2).strip()

    return data