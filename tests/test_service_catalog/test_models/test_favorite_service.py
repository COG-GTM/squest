from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from service_catalog.models import FavoriteService, Service


class TestFavoriteService(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("favorite-user")
        self.service = Service.objects.create(name="Favorite service")

    def test_unique_user_service_constraint(self):
        FavoriteService.objects.create(user=self.user, service=self.service)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FavoriteService.objects.create(user=self.user, service=self.service)

    def test_ordering_is_most_recent_first(self):
        second_service = Service.objects.create(name="Second service")
        first = FavoriteService.objects.create(user=self.user, service=self.service)
        second = FavoriteService.objects.create(user=self.user, service=second_service)
        self.assertEqual(list(FavoriteService.objects.all()), [second, first])

    def test_user_delete_cascades(self):
        FavoriteService.objects.create(user=self.user, service=self.service)
        self.user.delete()
        self.assertFalse(FavoriteService.objects.exists())

    def test_service_delete_cascades(self):
        FavoriteService.objects.create(user=self.user, service=self.service)
        self.service.delete()
        self.assertFalse(FavoriteService.objects.exists())
