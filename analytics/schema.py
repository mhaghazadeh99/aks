from django.db import models


def get_fields(model):
    fields = []

    for f in model._meta.fields:
        fields.append({
            "name": f.name,
            "type": f.get_internal_type(),
            "is_numeric": isinstance(f, (
                models.IntegerField,
                models.FloatField,
                models.DecimalField
            )),
            "is_date": isinstance(f, (
                models.DateField,
                models.DateTimeField
            )),
            "is_text": isinstance(f, (
                models.CharField,
                models.TextField
            )),
            "is_bool": isinstance(f, models.BooleanField),
        })

    return fields