from django.utils import timezone

from Squest.utils.datetime_widget import NativeDateTimeInput
from Squest.utils.squest_model_form import SquestModelForm
from profiles.models import Token


class TokenForm(SquestModelForm):
    class Meta:
        model = Token
        fields = ['description', 'expires']

    def __init__(self, *args, **kwargs):
        super(TokenForm, self).__init__(*args, **kwargs)
        min_date = timezone.now().astimezone().strftime("%Y-%m-%dT%H:%M")
        self.fields['expires'].widget = NativeDateTimeInput(attrs={'min': min_date})
