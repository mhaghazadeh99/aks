from django.db import models


def get_fields(model):
    fields = []

    for field in model._meta.fields:

        fields.append({
            "name": field.name,
            "type": field.get_internal_type(),

            "is_numeric": isinstance(field, (
                models.IntegerField,
                models.SmallIntegerField,
                models.BigIntegerField,
                models.PositiveIntegerField,
                models.PositiveSmallIntegerField,
                models.PositiveBigIntegerField,
                models.FloatField,
                models.DecimalField,
            )),

            "is_date": isinstance(field, (
                models.DateField,
                models.DateTimeField,
            )),

            "is_text": isinstance(field, (
                models.CharField,
                models.TextField,
            )),

            "is_bool": isinstance(
                field,
                models.BooleanField,
            ),
        })

    return fields