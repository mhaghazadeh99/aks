from django.http import JsonResponse
from .registry import MODEL_REGISTRY
from .schema import get_fields
from .semantic import detect_roles
from .query_engine import build_chart, build_time_series
from django.shortcuts import render
from django.db.models import F

# 👇 ADD THIS IMPORT (IMPORTANT)
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncQuarter,
    TruncYear
)


def models(request):
    return JsonResponse({
        "models": list(MODEL_REGISTRY.keys())
    })


def fields(request, model_key):
    model = MODEL_REGISTRY[model_key]
    fields = get_fields(model)

    semantic = detect_roles(fields)

    # =========================
    # 🔥 ADD DATE FIELDS TO MEASURES
    # =========================
    date_fields = [
        f["name"]
        for f in fields
        if "date" in f["type"].lower()
        or "time" in f["type"].lower()
        or "timestamp" in f["type"].lower()
    ]

    # Convert them into "measure-like objects"
    semantic["measures_extended"] = [
        {
            "name": f,
            "type": "date",
            "role": "temporal_measure"
        }
        for f in date_fields
    ]

    return JsonResponse({
        "fields": fields,
        "semantic": semantic
    })


def chart(request):
    model_key = request.GET.get("model")
    x = request.GET.get("x")
    measure = request.GET.get("measure")
    aggregation = request.GET.get("aggregation", "count")
    date_granularity = request.GET.get("date_granularity")
    time_measure = request.GET.get("time_measure")

    model = MODEL_REGISTRY[model_key]
    qs = model.objects.all()

    group_field = x

    # =========================
    # 🔥 TIME MODE (HIGHEST PRIORITY)
    # =========================
    if time_measure:

        if date_granularity == "day":
            qs = qs.annotate(group=TruncDay(F(time_measure)))
        elif date_granularity == "week":
            qs = qs.annotate(group=TruncWeek(F(time_measure)))
        elif date_granularity == "month":
            qs = qs.annotate(group=TruncMonth(F(time_measure)))
        elif date_granularity == "quarter":
            qs = qs.annotate(group=TruncQuarter(F(time_measure)))
        elif date_granularity == "year":
            qs = qs.annotate(group=TruncYear(F(time_measure)))
        else:
            qs = qs.annotate(group=TruncMonth(F(time_measure)))

        group_field = "group"
        x = None
        # time series usually behaves like COUNT unless explicitly measured
        if not measure:
            aggregation = "count"

    # =========================
    # 🔥 NORMAL DATE GROUPING (X axis)
    # =========================
    elif date_granularity and x:

        if date_granularity == "day":
            qs = qs.annotate(group=TruncDay(F(x)))
        elif date_granularity == "week":
            qs = qs.annotate(group=TruncWeek(F(x)))
        elif date_granularity == "month":
            qs = qs.annotate(group=TruncMonth(F(x)))
        elif date_granularity == "quarter":
            qs = qs.annotate(group=TruncQuarter(F(x)))
        elif date_granularity == "year":
            qs = qs.annotate(group=TruncYear(F(x)))

        group_field = "group"

    # =========================
    # BUILD CHART
    # =========================
    data, x_key, y_key = build_chart(
        qs,
        group_field,
        measure,
        aggregation,
    )

    return JsonResponse({
        "labels": [str(d[x_key]) for d in data],
        "values": [d[y_key] for d in data]
    })

def time_chart(request):
    model_key = request.GET.get("model")
    date_field = request.GET.get("date")
    measure = request.GET.get("measure")

    model = MODEL_REGISTRY[model_key]
    qs = model.objects.all()

    data, x_key, y_key = build_time_series(qs, date_field, measure)

    return JsonResponse({
        "labels": [str(d[x_key]) for d in data],
        "values": [d[y_key] for d in data]
    })


def analytics_home(request):
    return render(request, "analytics/analytics_home.html")