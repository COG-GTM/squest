from django.utils import timezone

from Squest.utils.datetime_widget import NativeDateTimeInput
from profiles.forms.token_forms import TokenForm
from tests.test_profiles.base.base_test_profile import BaseTestProfile


class TokenFormTests(BaseTestProfile):

    def test_expires_uses_native_datetime_widget_with_min_date(self):
        form = TokenForm()
        widget = form.fields['expires'].widget
        self.assertIsInstance(widget, NativeDateTimeInput)
        expected_min = timezone.now().astimezone().strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(expected_min, widget.attrs.get('min'))

    def test_expires_min_date_is_rendered(self):
        form = TokenForm()
        expected_min = timezone.now().astimezone().strftime("%Y-%m-%dT%H:%M")
        self.assertIn(f'min="{expected_min}"', str(form['expires']))
