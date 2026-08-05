from django.contrib import messages
from django.contrib.auth.models import User
from django.urls import reverse

from profiles.models import GlobalScope, Role
from profiles.models.squest_permission import Permission
from service_catalog.models.support import SupportState
from tests.test_service_catalog.base_test_request import BaseTestRequest


class TestAdminSupportBulkActions(BaseTestRequest):

    def _login_support_list_user(self, permissions):
        user = User.objects.create_user("support_list_user", password=self.common_password)
        role = Role.objects.create(name="Support list role")
        role.permissions.add(
            *Permission.objects.filter(
                content_type__app_label="service_catalog",
                codename__in=permissions,
            )
        )
        GlobalScope.load().add_user_in_role(user, role)
        self.client.login(username=user.username, password=self.common_password)

    def test_close_mixed_selection_only_closes_open_supports(self):
        self.support_test2.state = SupportState.CLOSED
        self.support_test2.save()
        url = reverse("service_catalog:support_bulk_close")

        response = self.client.get(url, data={"selection": [self.support_test.id, self.support_test2.id]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["object_list"]), [self.support_test])
        response = self.client.post(url, data={"selection": [self.support_test.id]})

        self.assertRedirects(response, reverse("service_catalog:support_list"))
        self.support_test.refresh_from_db()
        self.support_test2.refresh_from_db()
        self.assertEqual(self.support_test.state, SupportState.CLOSED)
        self.assertEqual(self.support_test2.state, SupportState.CLOSED)

    def test_reopen_mixed_selection_only_reopens_closed_supports(self):
        self.support_test.state = SupportState.CLOSED
        self.support_test.save()
        url = reverse("service_catalog:support_bulk_reopen")

        response = self.client.get(url, data={"selection": [self.support_test.id, self.support_test2.id]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["object_list"]), [self.support_test])
        response = self.client.post(url, data={"selection": [self.support_test.id]})

        self.assertRedirects(response, reverse("service_catalog:support_list"))
        self.support_test.refresh_from_db()
        self.support_test2.refresh_from_db()
        self.assertEqual(self.support_test.state, SupportState.OPENED)
        self.assertEqual(self.support_test2.state, SupportState.OPENED)

    def test_empty_selection_redirects(self):
        response = self.client.get(reverse("service_catalog:support_bulk_close"))

        self.assertRedirects(response, reverse("service_catalog:support_list"))

    def test_all_ineligible_selection_only_adds_skip_warning(self):
        self.support_test.state = SupportState.CLOSED
        self.support_test.save()

        response = self.client.get(
            reverse("service_catalog:support_bulk_close"),
            data={"selection": [self.support_test.id]},
        )

        warning_messages = list(messages.get_messages(response.wsgi_request))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(warning_messages), 1)
        self.assertIn("already closed", str(warning_messages[0]))
        self.assertNotIn("Empty selection", str(warning_messages[0]))

    def test_support_list_without_bulk_permission_has_no_add_button(self):
        self._login_support_list_user(["list_support", "view_support"])

        response = self.client.get(reverse("service_catalog:support_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["html_button_path"], "")

    def test_support_list_reopen_only_user_uses_reopen_action_url(self):
        self._login_support_list_user(["list_support", "view_support", "reopen_support"])

        response = self.client.get(reverse("service_catalog:support_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["action_url"],
            reverse("service_catalog:support_bulk_reopen"),
        )

    def test_user_without_permission_gets_forbidden(self):
        self.client.login(username=self.standard_user.username, password=self.common_password)

        response = self.client.get(
            reverse("service_catalog:support_bulk_close"),
            data={"selection": [self.support_test.id]},
        )

        self.assertEqual(response.status_code, 403)

    def test_logged_out_user_is_redirected(self):
        self.client.logout()

        response = self.client.get(
            reverse("service_catalog:support_bulk_close"),
            data={"selection": [self.support_test.id]},
        )

        self.assertEqual(response.status_code, 302)

    def test_post_selection_must_contain_only_permitted_supports(self):
        response = self.client.post(
            reverse("service_catalog:support_bulk_close"),
            data={"selection": [self.support_test.id, 999999]},
        )

        self.assertEqual(response.status_code, 403)
