from rest_framework.generics import ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from service_catalog.api.serializers import FavoriteServiceSerializer
from service_catalog.models import FavoriteService


class FavoriteServiceListCreate(ListCreateAPIView):
    serializer_class = FavoriteServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteService.objects.filter(
            user=self.request.user
        ).select_related("service")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FavoriteServiceDetails(RetrieveDestroyAPIView):
    serializer_class = FavoriteServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteService.objects.filter(
            user=self.request.user
        ).select_related("service")
