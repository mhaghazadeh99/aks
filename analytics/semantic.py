def detect_roles(fields):
    """
    Convert Django model fields into BI concepts.

    dimensions:
        text, boolean, foreign keys, etc.

    measures:
        numeric fields.

    time:
        date and datetime fields.
    """

    dimensions = []
    measures = []
    time_fields = []

    for field in fields:

        if field["is_date"]:
            time_fields.append(field["name"])

        elif field["is_numeric"]:
            measures.append(field["name"])

        else:
            dimensions.append(field["name"])

    return {
        "dimensions": dimensions,
        "measures": measures,
        "time": time_fields,
    }