from django.contrib.auth.models import User
from django.db import models

from Squest.utils.squest_model import SquestChangelog
from service_catalog.models.services import Service


class FavoriteService(SquestChangelog):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="favorite_services",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="favorite_entries",
    )

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "service"],
                name="unique_favorite_service",
            )
        ]
