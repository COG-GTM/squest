from django import forms


class NativeDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"
    format = "%Y-%m-%dT%H:%M"

    def __init__(self, attrs=None, format=None):
        widget_attrs = {"class": "form-control"}
        if attrs:
            widget_attrs.update(attrs)
        super().__init__(attrs=widget_attrs, format=format or self.format)
