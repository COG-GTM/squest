
from django.forms import Select, CheckboxInput, CheckboxSelectMultiple, RadioSelect, FileInput, DateTimeInput, Form

from Squest.utils.datetime_widget import NativeDateTimeInput


class SquestForm(Form):

    help_text = None
    error_css_class = 'is-invalid'

    def __init__(self, *args, **kwargs):
        super(SquestForm, self).__init__(*args, **kwargs)
        self.beautify()

    def is_valid(self):
        returned_value = super(SquestForm, self).is_valid()
        for field_name in self.errors.keys():
            if field_name != "__all__":
                current_class = self.fields.get(field_name).widget.attrs.get('class', '')
                self.fields.get(field_name).widget.attrs['class'] = f"{current_class} {self.error_css_class}"
        return returned_value

    def beautify(self):
        for field_name, current_field in self.fields.items():
            if isinstance(current_field.widget, Select):
                current_field.widget.attrs['class'] = 'selectpicker'
                current_field.widget.attrs['data-live-search'] = "true"
            elif isinstance(current_field.widget, CheckboxInput):
                current_field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(current_field.widget, CheckboxSelectMultiple):
                current_field.widget.attrs['class'] = 'form-control form-control-checkbox disable_list_style'
            elif isinstance(current_field.widget, RadioSelect):
                current_field.widget.attrs['class'] = "disable_list_style"
            elif isinstance(current_field.widget, FileInput):
                current_field.widget.attrs['class'] = ""
            elif isinstance(current_field.widget, DateTimeInput):
                current_field.widget = NativeDateTimeInput(attrs=current_field.widget.attrs)
            else:
                current_field.widget.attrs['class'] = 'form-control'
