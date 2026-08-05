from datetime import timedelta

from django.utils import timezone

from Squest.utils.datetime_widget import NativeDateTimeInput
from profiles.forms.token_forms import TokenForm
from tests.test_profiles.base.base_test_profile import BaseTestProfile


class TokenFormTests(BaseTestProfile):

    def test_expires_uses_native_datetime_widget_with_min_date(self):
        form = TokenForm()
        widget = form.fields['expires'].widget
        self.assertIsInstance(widget, NativeDateTimeInput)
        actual_min = timezone.datetime.fromisoformat(widget.attrs['min'])
        now = timezone.now().astimezone().replace(tzinfo=None, second=0, microsecond=0)
        self.assertGreaterEqual(actual_min, now)
        self.assertLessEqual(actual_min, now + timedelta(minutes=1))

    def test_expires_min_date_is_rendered(self):
        form = TokenForm()
        actual_min = form.fields['expires'].widget.attrs['min']
        self.assertIn(f'min="{actual_min}"', str(form['expires']))
