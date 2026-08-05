from django_tables2 import TemplateColumn, LinkColumn, CheckBoxColumn

from Squest.utils.squest_table import SquestTable
from service_catalog.models import Support


class SupportTable(SquestTable):
    selection = CheckBoxColumn(accessor='pk', attrs={"th__input": {"onclick": "toggle(this)"}})
    state = TemplateColumn(template_name='service_catalog/custom_columns/support_state.html')
    date_opened = TemplateColumn(template_name='generics/custom_columns/generic_date_format.html')
    title = LinkColumn()
    instance = LinkColumn()

    def before_render(self, request):
        if not (
            request.user.has_perm('service_catalog.close_support')
            or request.user.has_perm('service_catalog.reopen_support')
        ):
            self.columns.hide('selection')

    class Meta:
        model = Support
        attrs = {"id": "support_table", "class": "table squest-pagination-tables"}
        fields = ("selection", "title", "instance", "instance__service", "opened_by", "date_opened", "state")
