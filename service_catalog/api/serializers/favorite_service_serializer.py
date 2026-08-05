from rest_framework.serializers import ModelSerializer, ValidationError

from service_catalog.models import FavoriteService
from service_catalog.utils import get_orderable_services_for_user


class FavoriteServiceSerializer(ModelSerializer):
    class Meta:
        model = FavoriteService
        fields = ("id", "user", "service", "created", "last_updated")
        read_only_fields = ("id", "user", "created", "last_updated")

    def validate_service(self, service):
        user = self.context["request"].user
        if not get_orderable_services_for_user(
            user,
            filter_by_portfolio=False,
        ).filter(id=service.id).exists():
            raise ValidationError("You can only favorite services you can order.")
        if FavoriteService.objects.filter(user=user, service=service).exists():
            raise ValidationError("This service is already a favorite.")
        return service
