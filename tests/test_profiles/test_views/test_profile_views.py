from django.urls import reverse

from tests.test_profiles.base.base_test_profile import BaseTestProfile


class TestThemeSwitchView(BaseTestProfile):

    def setUp(self):
        super(TestThemeSwitchView, self).setUp()
        self.url = reverse('profiles:dark_light_theme_switch')
        self.referer = reverse('home')

    def test_switch_from_dark_to_light(self):
        profile = self.superuser.profile
        profile.theme = "dark"
        profile.save()
        response = self.client.get(self.url, HTTP_REFERER=self.referer)
        self.assertEqual(302, response.status_code)
        self.assertEqual(self.referer, response.url)
        profile.refresh_from_db()
        self.assertEqual("light", profile.theme)

    def test_switch_from_light_to_dark(self):
        profile = self.superuser.profile
        profile.theme = "light"
        profile.save()
        response = self.client.get(self.url, HTTP_REFERER=self.referer)
        self.assertEqual(302, response.status_code)
        self.assertEqual(self.referer, response.url)
        profile.refresh_from_db()
        self.assertEqual("dark", profile.theme)

    def test_switch_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url, HTTP_REFERER=self.referer)
        self.assertEqual(302, response.status_code)
        self.assertIn(reverse('login'), response.url)
