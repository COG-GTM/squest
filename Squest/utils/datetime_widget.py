from django import forms


class NativeDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"
    format = "%Y-%m-%dT%H:%M"

    def __init__(self, attrs=None):
        widget_attrs = {"class": "form-control", **(attrs or {})}
        super().__init__(attrs=widget_attrs, format=self.format)
