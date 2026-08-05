from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django_fsm import can_proceed

from Squest.utils.squest_views import *
from service_catalog.filters.support_filter import SupportFilter
from service_catalog.models import Support
from service_catalog.models.support import SupportState
from service_catalog.tables.support_tables import SupportTable


class SupportListView(SquestListView):
    table_class = SupportTable
    model = Support
    filterset_class = SupportFilter

    def get_queryset(self):
        return Support.get_queryset_for_user(self.request.user, 'service_catalog.view_support').prefetch_related(
            "instance", "opened_by", "instance__service").order_by("state")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['html_button_path'] = ""
        if (
            self.request.user.has_perm("service_catalog.close_support")
            or self.request.user.has_perm("service_catalog.reopen_support")
        ):
            context['html_button_path'] = "service_catalog/buttons/support_bulk_action_buttons.html"
            if self.request.user.has_perm("service_catalog.close_support"):
                context['action_url'] = reverse("service_catalog:support_bulk_close")
            else:
                context['action_url'] = reverse("service_catalog:support_bulk_reopen")
        return context


def _support_bulk_action(
    request,
    *,
    permission,
    target_state,
    transition,
    button_text,
    skip_message,
    card_class,
    button_class,
    icon,
    action_url,
    save_fields,
):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    pks = request.GET.getlist("selection") if request.method == "GET" else request.POST.getlist("selection")
    supports = Support.get_queryset_for_user(request.user, permission, unique=False).filter(pk__in=pks)

    if supports.count() != len(pks):
        raise PermissionDenied

    eligible = supports.filter(state=target_state)
    skipped = len(pks) - eligible.count()
    if skipped:
        messages.warning(request, f"{skipped} support(s) skipped because they are {skip_message}.")
    if not eligible:
        if not pks:
            messages.warning(request, "Empty selection.")
        return redirect("service_catalog:support_list")

    context = {
        "action_url": action_url,
        "button_text": button_text,
        "confirm_text": mark_safe(f"Confirm {button_text.lower()} of the following supports?"),
        "object_list": eligible,
        "card_class": card_class,
        "button_class": button_class,
        "icon": icon,
        "breadcrumbs": [
            {"text": "Support", "url": reverse("service_catalog:support_list")},
            {"text": f"{button_text} multiple", "url": ""},
        ],
    }

    if request.method == "GET":
        return render(request, "generics/confirm-bulk-action-template.html", context=context)

    for support in eligible:
        transition_method = transition(support)
        if can_proceed(transition_method):
            transition_method()
            support.save(update_fields=save_fields)
    return redirect("service_catalog:support_list")


@login_required
def support_bulk_close(request):
    return _support_bulk_action(
        request,
        permission="service_catalog.close_support",
        target_state=SupportState.OPENED,
        transition=lambda support: support.do_close,
        button_text="Close",
        skip_message="already closed",
        card_class="card-primary",
        button_class="btn-primary",
        icon="fa-check",
        action_url=reverse("service_catalog:support_bulk_close"),
        save_fields=["state", "date_closed"],
    )


@login_required
def support_bulk_reopen(request):
    return _support_bulk_action(
        request,
        permission="service_catalog.reopen_support",
        target_state=SupportState.CLOSED,
        transition=lambda support: support.do_open,
        button_text="Reopen",
        skip_message="already open",
        card_class="card-secondary",
        button_class="btn-secondary",
        icon="fa-undo",
        action_url=reverse("service_catalog:support_bulk_reopen"),
        save_fields=["state"],
    )


class SupportDeleteView(SquestDeleteView):
    model = Support

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'text': 'Instances', 'url': reverse('service_catalog:instance_list')},
            {'text': f"{self.object.instance.name} ({self.object.instance.id})",
             'url': reverse('service_catalog:instance_details', args=[self.object.instance.id])},
            {'text': f"Support - {self.object.title}", 'url': ''}
        ]
        return context


class ReOpenSupportView(SquestDetailView):
    model = Support
    permission_required = "service_catalog.reopen_support"

    def dispatch(self, request, *args, **kwargs):
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        super(ReOpenSupportView, self).dispatch(request, *args, **kwargs)
        support = self.get_object()
        support.do_open()
        support.save()
        return redirect(support.get_absolute_url())


class CloseSupportView(SquestDetailView):
    model = Support
    permission_required = "service_catalog.close_support"

    def dispatch(self, request, *args, **kwargs):
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        super(CloseSupportView, self).dispatch(request, *args, **kwargs)
        support = self.get_object()
        support.do_close()
        support.save()
        return redirect(support.get_absolute_url())
