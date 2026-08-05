from django.test import SimpleTestCase
from django.urls import reverse


class TestFavoriteServiceUrls(SimpleTestCase):
    def test_toggle_favorite_url(self):
        self.assertEqual(
            reverse(
                "service_catalog:toggle_favorite_service",
                kwargs={"service_id": 42},
            ),
            "/ui/service-catalog/service/42/favorite/",
        )

    def test_api_favorite_urls(self):
        self.assertEqual(
            reverse("api_favorite_service_list_create"),
            "/api/service-catalog/favorite-service/",
        )
        self.assertEqual(
            reverse(
                "api_favorite_service_details",
                kwargs={"pk": 42},
            ),
            "/api/service-catalog/favorite-service/42/",
        )
