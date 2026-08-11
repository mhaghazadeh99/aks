from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import F
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncQuarter,
    TruncYear,
)

from .registry import MODEL_REGISTRY
from .schema import get_fields
from .semantic import detect_roles
from .query_engine import build_chart, build_time_series


def models(request):
    return JsonResponse({
        "models": list(MODEL_REGISTRY.keys())
    })


def fields(request, model_key):
    model = MODEL_REGISTRY.get(model_key)

    if model is None:
        return JsonResponse(
            {"error": f"Unknown model: {model_key}"},
            status=404,
        )

    field_data = get_fields(model)

    semantic = detect_roles(field_data)

    # Date fields are also available as time-series measures
    date_fields = [
        f["name"]
        for f in field_data
        if f["is_date"]
    ]

    semantic["measures_extended"] = [
        {
            "name": field_name,
            "type": "date",
            "role": "temporal_measure",
        }
        for field_name in date_fields
    ]

    return JsonResponse({
        "fields": field_data,
        "semantic": semantic,
    })


def chart(request):
    model_key = request.GET.get("model")
    x = request.GET.get("x")
    measure = request.GET.get("measure") or None
    aggregation = request.GET.get("aggregation", "count")
    date_granularity = request.GET.get("date_granularity") or None
    time_measure = request.GET.get("time_measure") or None

    model = MODEL_REGISTRY.get(model_key)

    if model is None:
        return JsonResponse(
            {"error": f"Unknown model: {model_key}"},
            status=404,
        )

    # ---------------------------------
    # Validate model fields
    # ---------------------------------

    valid_fields = {
        field.name
        for field in model._meta.fields
    }

    if x and x not in valid_fields:
        return JsonResponse(
            {"error": f"Invalid X field: {x}"},
            status=400,
        )

    if measure and measure not in valid_fields:
        return JsonResponse(
            {"error": f"Invalid measure field: {measure}"},
            status=400,
        )

    if time_measure and time_measure not in valid_fields:
        return JsonResponse(
            {"error": f"Invalid time field: {time_measure}"},
            status=400,
        )

    qs = model.objects.all()

    group_field = x

    # ==========================================
    # TIME SERIES MODE
    # ==========================================

    if time_measure:

        if date_granularity == "day":
            qs = qs.annotate(
                group=TruncDay(time_measure)
            )

        elif date_granularity == "week":
            qs = qs.annotate(
                group=TruncWeek(time_measure)
            )

        elif date_granularity == "month":
            qs = qs.annotate(
                group=TruncMonth(time_measure)
            )

        elif date_granularity == "quarter":
            qs = qs.annotate(
                group=TruncQuarter(time_measure)
            )

        elif date_granularity == "year":
            qs = qs.annotate(
                group=TruncYear(time_measure)
            )

        else:
            qs = qs.annotate(
                group=TruncMonth(time_measure)
            )

        group_field = "group"

        # Temporal measure means:
        # COUNT records by date
        if not measure:
            aggregation = "count"

    # ==========================================
    # NORMAL DIMENSION DATE GROUPING
    # ==========================================

    elif date_granularity and x:

        if date_granularity == "day":
            qs = qs.annotate(
                group=TruncDay(x)
            )

        elif date_granularity == "week":
            qs = qs.annotate(
                group=TruncWeek(x)
            )

        elif date_granularity == "month":
            qs = qs.annotate(
                group=TruncMonth(x)
            )

        elif date_granularity == "quarter":
            qs = qs.annotate(
                group=TruncQuarter(x)
            )

        elif date_granularity == "year":
            qs = qs.annotate(
                group=TruncYear(x)
            )

        group_field = "group"

    # ==========================================
    # NORMAL CHART
    # ==========================================

    if not group_field:
        return JsonResponse(
            {"error": "No dimension or time field selected."},
            status=400,
        )

    data, x_key, y_key = build_chart(
        qs,
        group_field,
        measure,
        aggregation,
    )

    return JsonResponse({
        "labels": [str(row[x_key]) for row in data],
        "values": [row[y_key] for row in data],
    })


def time_chart(request):
    model_key = request.GET.get("model")
    date_field = request.GET.get("date")
    measure = request.GET.get("measure")

    model = MODEL_REGISTRY.get(model_key)

    if model is None:
        return JsonResponse(
            {"error": f"Unknown model: {model_key}"},
            status=404,
        )

    if not date_field:
        return JsonResponse(
            {"error": "Date field is required."},
            status=400,
        )

    if not measure:
        return JsonResponse(
            {"error": "Measure field is required."},
            status=400,
        )

    valid_fields = {
        field.name
        for field in model._meta.fields
    }

    if date_field not in valid_fields:
        return JsonResponse(
            {"error": f"Invalid date field: {date_field}"},
            status=400,
        )

    if measure not in valid_fields:
        return JsonResponse(
            {"error": f"Invalid measure field: {measure}"},
            status=400,
        )

    qs = model.objects.all()

    data, x_key, y_key = build_time_series(
        qs,
        date_field,
        measure,
    )

    return JsonResponse({
        "labels": [str(row[x_key]) for row in data],
        "values": [row[y_key] for row in data],
    })


def analytics_home(request):
    return render(
        request,
        "analytics/analytics_home.html",
    )