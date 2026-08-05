from django import forms
from django.utils import timezone

from Squest.utils.datetime_widget import NativeDateTimeInput
from Squest.utils.squest_model_form import SquestModelForm
from service_catalog.models.announcement import Announcement
from service_catalog.models.bootstrap_type import BootstrapType


class AnnouncementForm(SquestModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(AnnouncementForm, self).__init__(*args, **kwargs)
        widget_attrs = {}
        if self.instance.pk is None:
            min_date = timezone.now().astimezone().strftime("%Y-%m-%dT00:00")
            widget_attrs['min'] = min_date
        self.fields['date_start'].widget = NativeDateTimeInput(attrs=widget_attrs)
        self.fields['date_stop'].widget = NativeDateTimeInput(attrs=widget_attrs)
        now = timezone.now().astimezone().strftime("%Y-%m-%d %H:%M")
        tz_name = timezone.get_current_timezone()
        help_text = f"Time Zone is {tz_name} ({now})"
        self.fields['date_start'].help_text = help_text
        self.fields['date_stop'].help_text = help_text

    title = forms.CharField(label="Title",
                            widget=forms.TextInput())

    message = forms.CharField(label="Message",
                              help_text="HTML supported",
                              widget=forms.Textarea())

    date_start = forms.DateTimeField(label="Date start")

    date_stop = forms.DateTimeField(label="Date stop")

    type = forms.ChoiceField(label="Type",
                             choices=BootstrapType.choices,
                             initial=BootstrapType.INFO,
                             widget=forms.Select())

    class Meta:
        model = Announcement
        fields = ['title', 'message', 'date_start', 'date_stop', 'type']

    def save(self, commit=True):
        announcement = super().save(commit=False)
        announcement.created_by = self.user
        announcement.save()
        return announcement
