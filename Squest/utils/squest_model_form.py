from django.forms import ModelForm, Select, CheckboxInput, CheckboxSelectMultiple, RadioSelect, FileInput, \
    DateTimeInput, JSONField

from Squest.utils.datetime_widget import NativeDateTimeInput


class SquestModelForm(ModelForm):

    help_text = None
    error_css_class = 'is-invalid'

    def __init__(self, *args, **kwargs):
        super(SquestModelForm, self).__init__(*args, **kwargs)
        self.beautify()

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
                current_field.widget = NativeDateTimeInput()
            elif isinstance(current_field, JSONField):
                current_field.widget.attrs['class'] = 'form-control json'
                # current_field.widget.attrs['onblur'] = 'reformatJSON(this)'
            else:
                current_field.widget.attrs['class'] = 'form-control'

    def is_valid(self):
        returned_value = super(SquestModelForm, self).is_valid()
        for field_name in self.errors.keys():
            if field_name in self.fields.keys():
                current_class = self.fields.get(field_name).widget.attrs.get('class', '')
                self.fields.get(field_name).widget.attrs['class'] = f"{current_class} {self.error_css_class}"
        return returned_value
