from django.db.models import (
    Count,
    Sum,
    Avg,
    Min,
    Max,
)


AGGREGATIONS = {
    "count": Count,
    "sum": Sum,
    "avg": Avg,
    "min": Min,
    "max": Max,
}


def build_chart(
    qs,
    category,
    measure=None,
    aggregation="count",
):

    # ---------------------------------
    # COUNT RECORDS
    # ---------------------------------

    if aggregation == "count" or not measure:

        data = (
            qs
            .values(category)
            .annotate(
                value=Count("id")
            )
            .order_by(category)
        )

        return data, category, "value"

    # ---------------------------------
    # NUMERIC AGGREGATION
    # ---------------------------------

    agg_func = AGGREGATIONS.get(aggregation)

    if agg_func is None:
        raise ValueError(
            f"Unsupported aggregation: {aggregation}"
        )

    data = (
        qs
        .values(category)
        .annotate(
            value=agg_func(measure)
        )
        .order_by(category)
    )

    return data, category, "value"

def build_time_series(qs, date_field, measure):
    """
    PowerBI-style line chart
    """

    data = (
        qs.annotate(period=TruncMonth(date_field))
        .values("period")
        .annotate(value=Sum(measure))
        .order_by("period")
    )

    return data, "period", "value"