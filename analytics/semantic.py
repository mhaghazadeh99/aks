def detect_roles(fields):
    """
    Turns raw fields into BI meaning:
    - dimensions
    - measures
    - time
    """

    dimensions = []
    measures = []
    time_fields = []

    for f in fields:
        if f["is_date"]:
            time_fields.append(f["name"])

        elif f["is_numeric"]:
            measures.append(f["name"])

        else:
            dimensions.append(f["name"])

    return {
        "dimensions": dimensions,
        "measures": measures,
        "time": time_fields
    }