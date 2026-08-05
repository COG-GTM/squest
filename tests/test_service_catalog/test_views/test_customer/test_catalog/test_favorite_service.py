from django.urls import reverse

from service_catalog.models import FavoriteService
from tests.test_service_catalog.base_test_request import BaseTestRequest


class TestFavoriteServiceView(BaseTestRequest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.standard_user)
        self.url = reverse(
            "service_catalog:toggle_favorite_service",
            kwargs={"service_id": self.service_test.id},
        )

    def test_add_favorite(self):
        response = self.client.post(self.url, {"next": "/ui/service-catalog/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/ui/service-catalog/")
        self.assertTrue(
            FavoriteService.objects.filter(
                user=self.standard_user,
                service=self.service_test,
            ).exists()
        )

    def test_remove_favorite(self):
        FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        self.client.post(self.url)
        self.assertFalse(
            FavoriteService.objects.filter(
                user=self.standard_user,
                service=self.service_test,
            ).exists()
        )

    def test_get_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unauthenticated_redirects_to_login(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_non_orderable_service_is_forbidden(self):
        self.create_operation_test.permission = self.admin_operation
        self.create_operation_test.enabled = False
        self.create_operation_test.save()
        self.service_test.enabled = False
        self.service_test.save()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    def test_external_next_is_ignored(self):
        response = self.client.post(self.url, {"next": "https://evil.example/"})
        self.assertEqual(
            response["Location"],
            reverse("service_catalog:service_catalog_list"),
        )


class TestCatalogPersonalization(BaseTestRequest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.standard_user)

    def test_root_shows_favorites_and_recent_services(self):
        FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        recent_instance = self.test_instance.__class__.objects.create(
            name="recent-instance",
            service=self.service_test_2,
            quota_scope=self.test_quota_scope_org,
            requester=self.standard_user,
        )
        self.test_request.__class__.objects.create(
            instance=recent_instance,
            operation=self.create_operation_test_2,
            user=self.standard_user,
        )
        response = self.client.get(reverse("service_catalog:service_catalog_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [service.id for service in response.context["favorites"]],
            [self.service_test.id],
        )
        self.assertEqual(
            [service.id for service in response.context["recently_ordered"]],
            [self.service_test_2.id],
        )

    def test_personalized_rows_are_absent_inside_portfolio(self):
        self.service_test.parent_portfolio = self.portfolio_test_1
        self.service_test.save()
        response = self.client.get(
            reverse("service_catalog:service_catalog_list"),
            {"parent_portfolio": self.portfolio_test_1.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["favorites"], [])
        self.assertEqual(response.context["recently_ordered"], [])

    def test_lost_permission_removes_favorite_from_catalog(self):
        FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        self.create_operation_test.permission = self.admin_operation
        self.create_operation_test.save()
        response = self.client.get(reverse("service_catalog:service_catalog_list"))
        self.assertEqual(response.context["favorites"], [])

    def test_recent_services_exclude_favorites(self):
        FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        response = self.client.get(reverse("service_catalog:service_catalog_list"))
        self.assertNotIn(
            self.service_test,
            response.context["recently_ordered"],
        )
