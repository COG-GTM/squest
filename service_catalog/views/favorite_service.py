from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from service_catalog.models import FavoriteService, Service
from service_catalog.utils import get_orderable_services_for_user


@login_required
@require_POST
def toggle_favorite_service(request, service_id):
    service = get_object_or_404(Service, id=service_id)
    if not get_orderable_services_for_user(
        request.user,
        filter_by_portfolio=False,
    ).filter(id=service.id).exists():
        raise PermissionDenied

    favorite, created = FavoriteService.objects.get_or_create(
        user=request.user,
        service=service,
    )
    if not created:
        favorite.delete()

    next_url = request.POST.get("next")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("service_catalog:service_catalog_list")
    return redirect(next_url)
