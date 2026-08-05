from rest_framework import status
from rest_framework.reverse import reverse

from service_catalog.models import FavoriteService
from tests.test_service_catalog.base_test_request import BaseTestRequestAPI


class TestFavoriteServiceAPI(BaseTestRequestAPI):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.standard_user)
        self.list_url = reverse("api_favorite_service_list_create")

    def test_list_only_returns_current_users_favorites(self):
        own = FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        FavoriteService.objects.create(
            user=self.standard_user_2,
            service=self.service_test_2,
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], own.id)

    def test_create_favorite(self):
        response = self.client.post(
            self.list_url,
            {"service": self.service_test.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["service"], self.service_test.id)
        self.assertEqual(response.data["user"], self.standard_user.id)

    def test_create_non_orderable_service_is_rejected(self):
        self.create_operation_test.permission = self.admin_operation
        self.create_operation_test.enabled = False
        self.create_operation_test.save()
        self.service_test.enabled = False
        self.service_test.save()
        response = self.client.post(
            self.list_url,
            {"service": self.service_test.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_create_is_rejected(self):
        FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        response = self.client.post(
            self.list_url,
            {"service": self.service_test.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_own_favorite(self):
        favorite = FavoriteService.objects.create(
            user=self.standard_user,
            service=self.service_test,
        )
        response = self.client.delete(
            reverse(
                "api_favorite_service_details",
                kwargs={"pk": favorite.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_cannot_delete_another_users_favorite(self):
        favorite = FavoriteService.objects.create(
            user=self.standard_user_2,
            service=self.service_test_2,
        )
        response = self.client.delete(
            reverse(
                "api_favorite_service_details",
                kwargs={"pk": favorite.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_is_rejected(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )
