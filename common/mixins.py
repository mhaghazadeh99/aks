from django.db import models

from common.forms import get_date_widget


class PersianDateMixin:

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        widget = get_date_widget()

        for field_name, field in self.fields.items():

            model_field = self._meta.model._meta.get_field(field_name)

            if isinstance(model_field, models.DateField):

                field.widget = widget()