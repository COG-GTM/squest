"""Resource tracking and quotas: the capacity side of the portal.

Covers the "Resource tracking" sidebar group: attribute definitions, resource groups and their
transformers, the resources they hold, the produced/consumed totals a capacity decision is read off,
the topology graph, and the quotas of an organization and of a team, as the admin who administers
them and as the scoped user who may only read his own scope.
"""
import uuid

from playwright.sync_api import expect

from e2e.helpers import NAV_MAP, expect_form_error, expect_table_contains, expect_table_does_not_contain, \
    goto_sidebar_entry, submit_form, table_row, table_rows, visible_sidebar_entries

SEEDED_PROVIDER_GROUP = "Physical servers"
SEEDED_CONSUMER_GROUP = "VMware cluster"
SEEDED_ATTRIBUTE = "vCPU"


def _unique(prefix):
    """The seed is shared and ``E2E_REUSE_DB`` may keep it between runs, so every object is unique."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_attribute_definition(page, name, description=""):
    goto_sidebar_entry(page, "Attributes")
    page.get_by_role("link", name="Add").click()
    page.fill("input[name='name']", name)
    page.fill("input[name='description']", description)
    submit_form(page, "Add")


def _create_resource_group(page, name):
    goto_sidebar_entry(page, "Resource groups")
    page.get_by_role("link", name="Add").click()
    page.fill("input[name='name']", name)
    submit_form(page, "Add")


def _filter_named_list(page, name, expect_one=True):
    filter_name = page.locator("aside.control-sidebar input[name='name']")
    expect(filter_name).to_have_count(1)
    filter_toggle = page.locator("a.btn[data-widget='control-sidebar']")
    expect(filter_toggle).to_have_count(1)
    filter_toggle.first.click()
    expect(filter_name).to_be_visible()
    filter_name.fill(name)
    apply_button = page.locator("aside.control-sidebar").get_by_role("button", name="Apply")
    expect(apply_button).to_have_count(1)
    apply_button.click()
    page.wait_for_load_state()
    if expect_one:
        expect(table_row(page, name)).to_have_count(1)


def _goto_named_list_row(page, sidebar_entry, name, expect_one=True):
    goto_sidebar_entry(page, sidebar_entry)
    _filter_named_list(page, name, expect_one=expect_one)


def _show_all_filtered_rows(page):
    filter_toggle = page.locator("a.btn[data-widget='control-sidebar']")
    expect(filter_toggle).to_have_count(1)
    filter_toggle.first.click()
    per_page = page.locator("aside.control-sidebar select[name='per_page']")
    expect(per_page).to_have_count(1)
    expect(per_page).to_be_visible()
    per_page.select_option("1000")
    apply_button = page.locator("aside.control-sidebar").get_by_role("button", name="Apply")
    expect(apply_button).to_have_count(1)
    apply_button.click()
    page.wait_for_load_state()


def _goto_resource_group_attributes(page, group_name):
    """The transformer list of a group, through the attribute count button of its list row."""
    _goto_named_list_row(page, "Resource groups", group_name)
    table_row(page, group_name).locator("a[href$='/attribute/']").click()
    page.wait_for_load_state()


def _goto_resource_group_resources(page, group_name):
    """The resource list of a group, through the resource count button of its list row."""
    _goto_named_list_row(page, "Resource groups", group_name)
    table_row(page, group_name).locator("a[href$='/resource/']").click()
    page.wait_for_load_state()


def _add_transformer(page, group_name, attribute, consume_from_group=None, consume_from_attribute=None):
    """Adds an attribute (a transformer) on a group, optionally consuming from another group."""
    _goto_resource_group_attributes(page, group_name)
    page.get_by_role("link", name="Add").click()
    page.select_option("#id_attribute_definition", label=attribute)
    if consume_from_group is not None:
        page.select_option("#id_consume_from_resource_group", label=consume_from_group)
        # the target attribute list is filled by an ajax call fired by the resource group change
        target_option = page.locator("#id_consume_from_attribute_definition option",
                                     has_text=consume_from_attribute)
        expect(target_option).to_have_count(1)
        page.select_option("#id_consume_from_attribute_definition", label=consume_from_attribute)
    page.get_by_role("button", name="Add attribute").click()
    page.wait_for_load_state()


def _create_resource(page, group_name, name, attribute_values):
    _goto_resource_group_resources(page, group_name)
    page.get_by_role("link", name="Add").click()
    page.fill("input[name='name']", name)
    for attribute, value in attribute_values.items():
        page.get_by_label(attribute, exact=True).fill(str(value))
    submit_form(page, "Add")


def _edit_resource(page, group_name, name, attribute_values):
    _goto_resource_group_resources(page, group_name)
    table_row(page, name).locator("a[href*='/edit/']").click()
    page.wait_for_load_state()
    for attribute, value in attribute_values.items():
        page.get_by_label(attribute, exact=True).fill(str(value))
    submit_form(page, "Update")


def _goto_resource_named_list_row(page, group_name, name, expect_one=True):
    _goto_resource_group_resources(page, group_name)
    _filter_named_list(page, name, expect_one=expect_one)


def _resource_values(page, name):
    row = table_row(page, name)
    expect(row).to_have_count(1)
    headers = [text.strip() for text in page.locator("#resource_table thead th").all_inner_texts()]
    cells = [text.strip() for text in row.locator("td").all_inner_texts()]
    return dict(zip(headers, cells))


def _resource_attribute_value(values, attribute):
    header = next((header for header in values if header.casefold() == attribute.casefold()), None)
    assert header is not None, f"resource table has no '{attribute}' column: {list(values)}"
    return values[header]


def _group_totals(page, group_name):
    """The produced/consumed/available totals of a group, read off the 'Table view' of the list.

    Returns a ``{'vCPU produced': '10', ...}`` mapping, the header of the column being the label the
    user reads the number under.
    """
    goto_sidebar_entry(page, "Resource groups")
    page.get_by_role("link", name="Table view").click()
    page.wait_for_load_state()
    headers = [text.strip() for text in page.locator("#resource_group_table_csv thead th").all_inner_texts()]
    row = page.locator("#resource_group_table_csv tbody tr").filter(has_text=group_name).first
    expect(row).to_be_visible()
    cells = [text.strip() for text in row.locator("td").all_inner_texts()]
    return dict(zip(headers, cells))


def _goto_scope_quotas(page, scope_entry, scope_name):
    """A scope detail page, opened on its quota tab: Access -> Organization|Team -> the scope."""
    _goto_named_list_row(page, scope_entry, scope_name)
    table_row(page, scope_name).get_by_role("link", name=scope_name, exact=True).first.click()
    page.wait_for_load_state()
    page.get_by_role("link", name="Quotas", exact=True).click()


def _quota_row(page, attribute):
    return table_rows(page).filter(
        has=page.get_by_role("link", name=attribute, exact=True)
    )


# --- attribute definitions ---------------------------------------------------------------------


def test_admin_creates_an_attribute_definition(admin_page):
    name = _unique("GPU")
    _create_attribute_definition(admin_page, name, "Graphic cards of the hypervisor")

    expect(admin_page.locator("h3.card-title")).to_contain_text(name)
    expect(admin_page.locator("body")).to_contain_text("Graphic cards of the hypervisor")


def test_admin_edits_an_attribute_definition(admin_page):
    name = _unique("IOPS")
    renamed = _unique("IOPS-renamed")
    _create_attribute_definition(admin_page, name, "First description")

    _goto_named_list_row(admin_page, "Attributes", name)
    table_row(admin_page, name).get_by_title("Edit").click()
    admin_page.fill("input[name='name']", renamed)
    admin_page.fill("input[name='description']", "Second description")
    submit_form(admin_page, "Update")

    _goto_named_list_row(admin_page, "Attributes", renamed)
    expect(table_row(admin_page, renamed)).to_contain_text("Second description")

    _goto_named_list_row(admin_page, "Attributes", name, expect_one=False)
    expect_table_does_not_contain(admin_page, name)


def test_admin_deletes_an_attribute_definition(admin_page):
    name = _unique("Bandwidth")
    _create_attribute_definition(admin_page, name, "To be removed")

    _goto_named_list_row(admin_page, "Attributes", name)
    table_row(admin_page, name).get_by_title("Delete").click()
    expect(admin_page.locator("body")).to_contain_text(f"Confirm deletion of {name}")
    submit_form(admin_page, "Confirm")

    _goto_named_list_row(admin_page, "Attributes", name, expect_one=False)
    expect_table_does_not_contain(admin_page, name)


def test_an_attribute_name_colliding_with_an_existing_one_is_rejected(admin_page):
    _create_attribute_definition(admin_page, SEEDED_ATTRIBUTE, "A second vCPU attribute")

    expect_form_error(admin_page, "already exists")


# --- resource groups and their transformers ------------------------------------------------------


def test_admin_creates_a_resource_group_and_adds_its_attributes(admin_page):
    group = _unique("Blade chassis")
    _create_resource_group(admin_page, group)
    expect(admin_page.locator("ol.breadcrumb li.active")).to_contain_text(group)

    _add_transformer(admin_page, group, SEEDED_ATTRIBUTE)
    _add_transformer(admin_page, group, "Memory", consume_from_group=SEEDED_PROVIDER_GROUP,
                     consume_from_attribute="Memory")

    expect_table_contains(admin_page, SEEDED_ATTRIBUTE)
    memory_row = table_row(admin_page, "Memory")
    expect(memory_row).to_contain_text(SEEDED_PROVIDER_GROUP)


def test_admin_deletes_a_resource_group(admin_page):
    group = _unique("Retired rack")
    _create_resource_group(admin_page, group)
    _add_transformer(admin_page, group, SEEDED_ATTRIBUTE)

    _goto_named_list_row(admin_page, "Resource groups", group)
    table_row(admin_page, group).get_by_title("Delete").click()
    submit_form(admin_page, "Confirm")

    _goto_named_list_row(admin_page, "Resource groups", group, expect_one=False)
    expect_table_does_not_contain(admin_page, group)


# --- resources ------------------------------------------------------------------------------------


def test_admin_creates_a_resource_and_edits_its_attribute_values(admin_page):
    group = _unique("Storage array")
    resource = _unique("disk")
    _create_resource_group(admin_page, group)
    _add_transformer(admin_page, group, SEEDED_ATTRIBUTE)
    _add_transformer(admin_page, group, "Storage")

    _create_resource(admin_page, group, resource, {SEEDED_ATTRIBUTE: 8, "Storage": 512})
    values = _resource_values(admin_page, resource)
    assert _resource_attribute_value(values, SEEDED_ATTRIBUTE) == "8"
    assert _resource_attribute_value(values, "Storage") == "512"

    _edit_resource(admin_page, group, resource, {"Storage": 1024})
    values = _resource_values(admin_page, resource)
    assert _resource_attribute_value(values, SEEDED_ATTRIBUTE) == "8"
    assert _resource_attribute_value(values, "Storage") == "1024"


def test_admin_moves_a_resource_to_another_resource_group(admin_page):
    source = _unique("Source rack")
    target = _unique("Target rack")
    resource = _unique("node")
    _create_resource_group(admin_page, source)
    _add_transformer(admin_page, source, SEEDED_ATTRIBUTE)
    _create_resource_group(admin_page, target)
    _add_transformer(admin_page, target, SEEDED_ATTRIBUTE)
    _create_resource(admin_page, source, resource, {SEEDED_ATTRIBUTE: 16})

    table_row(admin_page, resource).get_by_title("Move resource to another resource group").click()
    admin_page.select_option("#id_resource_group", label=target)
    submit_form(admin_page, "Update")

    _goto_resource_group_resources(admin_page, target)
    expect_table_contains(admin_page, resource)
    _goto_resource_group_resources(admin_page, source)
    expect_table_does_not_contain(admin_page, resource)


def test_admin_deletes_a_resource_and_bulk_deletes_the_remaining_ones(admin_page):
    group = _unique("Decommission pool")
    deleted_alone = _unique("alone")
    bulk_first = _unique("bulk-first")
    bulk_second = _unique("bulk-second")
    _create_resource_group(admin_page, group)
    _add_transformer(admin_page, group, SEEDED_ATTRIBUTE)
    for name in [deleted_alone, bulk_first, bulk_second]:
        _create_resource(admin_page, group, name, {SEEDED_ATTRIBUTE: 2})

    _goto_resource_named_list_row(admin_page, group, deleted_alone)
    table_row(admin_page, deleted_alone).locator("a[href*='/delete/']").click()
    submit_form(admin_page, "Confirm")
    _goto_resource_named_list_row(admin_page, group, deleted_alone, expect_one=False)
    expect_table_does_not_contain(admin_page, deleted_alone)

    _goto_resource_group_resources(admin_page, group)
    for name in [bulk_first, bulk_second]:
        table_row(admin_page, name).locator("input[name='selection']").check()
    admin_page.get_by_role("button", name="Delete").click()
    admin_page.wait_for_load_state()
    expect(admin_page.locator("body")).to_contain_text("Confirm deletion of the following resources?")
    submit_form(admin_page, "Delete")

    _goto_resource_named_list_row(admin_page, group, bulk_first, expect_one=False)
    expect_table_does_not_contain(admin_page, bulk_first)
    _goto_resource_named_list_row(admin_page, group, bulk_second, expect_one=False)
    expect_table_does_not_contain(admin_page, bulk_second)
    _goto_named_list_row(admin_page, "Resource groups", group)
    expect(table_row(admin_page, group)).to_have_count(1)


# --- the totals a capacity decision is read off ----------------------------------------------------


def test_group_totals_follow_the_attribute_values_of_their_resources(admin_page):
    """A consumer group consuming a provider group, the way 'VMware cluster' consumes 'Physical servers'."""
    provider = _unique("Provider pool")
    consumer = _unique("Consumer pool")
    _create_resource_group(admin_page, provider)
    _add_transformer(admin_page, provider, SEEDED_ATTRIBUTE)
    _create_resource_group(admin_page, consumer)
    _add_transformer(admin_page, consumer, SEEDED_ATTRIBUTE, consume_from_group=provider,
                     consume_from_attribute=SEEDED_ATTRIBUTE)

    _create_resource(admin_page, provider, _unique("hypervisor"), {SEEDED_ATTRIBUTE: 10})
    consumer_resource = _unique("guest")
    _create_resource(admin_page, consumer, consumer_resource, {SEEDED_ATTRIBUTE: 4})

    totals = _group_totals(admin_page, provider)
    assert totals[f"{SEEDED_ATTRIBUTE} produced"] == "10"
    assert totals[f"{SEEDED_ATTRIBUTE} consumed"] == "4"
    assert totals[f"{SEEDED_ATTRIBUTE} available"] == "6"

    _edit_resource(admin_page, consumer, consumer_resource, {SEEDED_ATTRIBUTE: 6})

    totals = _group_totals(admin_page, provider)
    assert totals[f"{SEEDED_ATTRIBUTE} consumed"] == "6"
    assert totals[f"{SEEDED_ATTRIBUTE} available"] == "4"
    assert _group_totals(admin_page, consumer)[f"{SEEDED_ATTRIBUTE} produced"] == "6"


def test_the_graph_renders_the_resource_group_topology(admin_page):
    goto_sidebar_entry(admin_page, "Graph")

    expect(admin_page.locator("h1")).to_contain_text("Resource Tracker Graph")
    graph = admin_page.locator("svg:not([data-icon])").first
    expect(graph).to_be_visible()
    expect(graph).to_contain_text(SEEDED_PROVIDER_GROUP)
    expect(graph).to_contain_text(SEEDED_CONSUMER_GROUP)


# --- quotas ------------------------------------------------------------------------------------


def test_the_quota_list_shows_the_seeded_limit_of_every_scope(admin_page):
    goto_sidebar_entry(admin_page, "Quota")
    _show_all_filtered_rows(admin_page)

    # The filter sidebar displays all seeded scope quotas despite the list's default pagination.
    platform_engineering = table_rows(admin_page).filter(
        has=admin_page.get_by_role("link", name="Platform Engineering", exact=True)
    ).filter(
        has=admin_page.get_by_role("link", name="Memory", exact=True)
    )
    expect(platform_engineering).to_have_count(1)
    expect(platform_engineering).to_contain_text("512")
    sre = table_rows(admin_page).filter(
        has=admin_page.get_by_role("link", name="Platform Engineering - SRE", exact=True)
    ).filter(
        has=admin_page.get_by_role("link", name="Memory", exact=True)
    )
    expect(sre).to_have_count(1)
    expect(sre).to_contain_text("128")


def test_admin_changes_the_quota_limit_of_a_team(admin_page):
    """The 'Data' team is the one no other test reads, so its limit can move."""
    _goto_scope_quotas(admin_page, "Team", "Data")
    admin_page.get_by_role("link", name="Set quotas").click()
    admin_page.wait_for_load_state()
    memory_field = admin_page.get_by_label("Memory", exact=True)
    new_limit = 120 if memory_field.input_value().strip() != "120" else 124
    memory_field.fill(str(new_limit))
    submit_form(admin_page, "Update")

    expect(_quota_row(admin_page, "Memory")).to_contain_text(str(new_limit))


def test_the_quota_of_a_scope_shows_what_its_instances_consume(admin_page):
    """batch-worker-01 is the only instance of the 'SRE' team, and it holds 8 vCPU."""
    _goto_scope_quotas(admin_page, "Team", "SRE")
    _quota_row(admin_page, SEEDED_ATTRIBUTE).get_by_role("link", name="8", exact=True).click()
    admin_page.wait_for_load_state()

    limit = admin_page.locator(".info-box", has_text="Limit")
    expect(limit).to_contain_text("32")
    consumption = admin_page.locator(".info-box", has_text="Instances consumption")
    expect(consumption).to_contain_text("8")
    expect(admin_page.locator("body")).to_contain_text("batch-worker-01")


# --- what the scoped non admin sees ---------------------------------------------------------------


def test_scoped_user_reads_the_quota_of_his_scope_without_being_able_to_change_it(scoped_user_page):
    _goto_scope_quotas(scoped_user_page, "Organization", "Platform Engineering")

    expect(_quota_row(scoped_user_page, SEEDED_ATTRIBUTE)).to_contain_text("128")
    expect(scoped_user_page.get_by_role("link", name="Set quotas")).to_have_count(0)


def test_scoped_user_does_not_see_another_organization(scoped_user_page):
    goto_sidebar_entry(scoped_user_page, "Organization")

    expect_table_contains(scoped_user_page, "Platform Engineering")
    expect_table_does_not_contain(scoped_user_page, "Marketing")


def test_the_resource_tracking_administration_answers_403_to_the_scoped_user(scoped_user_page, base_url):
    entries = visible_sidebar_entries(scoped_user_page)
    for hidden in ["Attributes", "Resource groups", "Graph", "Quota"]:
        assert hidden not in entries, f"the scoped user must not see the '{hidden}' entry"

    for name, path in NAV_MAP["Resource tracking"].items():
        response = scoped_user_page.goto(f"{base_url}{path}")
        assert response.status == 403, f"the scoped user got {response.status} on '{name}' ({path})"
