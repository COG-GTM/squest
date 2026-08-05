"""The front door of Squest: browsing the service catalog and submitting a request.

Covers what a consumer walks through before anything else exists: the catalog and its portfolios,
the two step request wizard (instance name + quota scope, then the survey), the survey bounds, the
quota scope boundary, and the catalog administration that makes a service requestable.

The lifecycle of a request once it is submitted (accept/reject/process/approval) belongs to another
spec: this one stops at SUBMITTED.
"""
import re
import uuid
from urllib.parse import urlparse

from playwright.sync_api import Page, expect

from e2e.helpers import (
    expect_table_contains,
    expect_table_does_not_contain,
    goto_sidebar_entry,
    submit_form,
    table_row,
)

DEMO_JOB_TEMPLATE = "Deploy virtual machine (Demo AAP)"


def _unique(prefix: str) -> str:
    """A name no other test, and no previous run against a kept database, can collide with."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _catalog_card(page: Page, name: str):
    """A portfolio or service card of the service catalog page, found by its title."""
    return page.locator(f"div.card:has(h5.card-title strong:text-is('{name}'))")


def _open_portfolio(page: Page, name: str) -> None:
    _catalog_card(page, name).get_by_role("link", name="Open").click()
    page.wait_for_load_state()


def _order_service(page: Page, name: str) -> None:
    """Clicks 'Order' on a service card, which lands on the first step of the request wizard."""
    _catalog_card(page, name).get_by_role("link", name="Order").click()
    page.wait_for_load_state()


def _pick(page: Page, field_name: str, label: str) -> None:
    """Picks an option of a select. Squest dresses every select as a bootstrap-select dropdown."""
    dropdown = page.locator(f"div.bootstrap-select:has(select[name='{field_name}'])")
    if dropdown.count() == 1:
        dropdown.locator("button.dropdown-toggle").click()
        options = dropdown.locator(".dropdown-menu li a")
        option_texts = [text.strip() for text in options.all_inner_texts()]
        selected_label = next(
            (text for text in option_texts if text == label or text.endswith(f" - {label}")),
            None,
        )
        if selected_label is None:
            page.select_option(f"select[name='{field_name}']", label=label, force=True)
        else:
            options.filter(has_text=re.compile(rf"^\s*{re.escape(selected_label)}\s*$")).click()
    else:
        page.select_option(f"select[name='{field_name}']", label=label, force=True)


def _option_labels(page: Page, field_name: str) -> list[str]:
    return [text.strip() for text in page.locator(f"select[name='{field_name}'] option").all_inner_texts()]


def _submit_wizard_step(page: Page) -> None:
    """The wizard template validates with an ``input``, and its only ``button`` goes back a step."""
    page.locator("form input[type='submit']").click()
    page.wait_for_load_state()


def _fill_first_step(page: Page, instance_name: str, quota_scope: str) -> None:
    page.fill("input[name='0-name']", instance_name)
    _pick(page, "0-quota_scope", quota_scope)
    _submit_wizard_step(page)


def _fill_survey_step(page: Page, vcpu: int, memory: int, environment: str) -> None:
    page.fill("input[name='1-vcpu']", str(vcpu))
    page.fill("input[name='1-memory']", str(memory))
    _pick(page, "1-environment", environment)


def _create_portfolio(admin_page: Page, name: str) -> None:
    goto_sidebar_entry(admin_page, "Service catalog")
    admin_page.get_by_role("link", name="All portfolios").click()
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    submit_form(admin_page)
    _filter_portfolios(admin_page, name)
    expect_table_contains(admin_page, name)


def _filter_portfolios(admin_page: Page, name: str) -> None:
    """Finds a portfolio even when a kept database has more than one table page."""
    goto_sidebar_entry(admin_page, "Service catalog")
    admin_page.get_by_role("link", name="All portfolios").click()
    admin_page.wait_for_load_state()
    admin_page.locator("a[data-widget='control-sidebar']").first.click()
    admin_page.locator("input[name='name']").fill(name)
    admin_page.get_by_role("button", name="Apply", exact=True).click()
    admin_page.wait_for_load_state()


def _create_service(admin_page: Page, name: str, portfolio_name: str) -> None:
    goto_sidebar_entry(admin_page, "Service catalog")
    admin_page.get_by_role("link", name="All services").click()
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    _pick(admin_page, "parent_portfolio", portfolio_name)
    submit_form(admin_page)
    _filter_services(admin_page, name)
    expect_table_contains(admin_page, name)


def _filter_services(admin_page: Page, name: str) -> None:
    """Finds a service even when a kept database has more than one table page."""
    goto_sidebar_entry(admin_page, "Service catalog")
    admin_page.get_by_role("link", name="All services").click()
    admin_page.wait_for_load_state()
    admin_page.locator("a[data-widget='control-sidebar']").first.click()
    admin_page.locator("input[name='name']").fill(name)
    admin_page.get_by_role("button", name="Apply", exact=True).click()
    admin_page.wait_for_load_state()


def _open_service(admin_page: Page, name: str) -> None:
    _filter_services(admin_page, name)
    table_row(admin_page, name).get_by_role("link").first.click()
    admin_page.wait_for_load_state()


def _add_create_operation(admin_page: Page, service_name: str, operation_name: str) -> None:
    """Adds a CREATE operation bound to the stubbed job template, which enables the service."""
    _open_service(admin_page, service_name)
    admin_page.get_by_role("link", name="Add operation").click()
    admin_page.fill("input[name='name']", operation_name)
    _pick(admin_page, "job_template", DEMO_JOB_TEMPLATE)
    submit_form(admin_page)


def _create_requestable_service(admin_page: Page) -> tuple[str, str, str]:
    """Portfolio + service + create operation, the whole administration path a catalog owner walks."""
    portfolio_name = _unique("Portfolio")
    service_name = _unique("Service")
    operation_name = _unique("Create")
    _create_portfolio(admin_page, portfolio_name)
    _create_service(admin_page, service_name, portfolio_name)
    _add_create_operation(admin_page, service_name, operation_name)
    return portfolio_name, service_name, operation_name


def test_scoped_user_browses_the_catalog_from_the_sidebar(scoped_user_page):
    """bob reaches the catalog the way a consumer does and drills down to a service."""
    goto_sidebar_entry(scoped_user_page, "Service catalog")
    expect(scoped_user_page).to_have_url(re.compile(r"/service-catalog/$"))
    expect(_catalog_card(scoped_user_page, "Infrastructure")).to_have_count(1)

    _open_portfolio(scoped_user_page, "Infrastructure")
    expect(_catalog_card(scoped_user_page, "Virtual machine")).to_have_count(1)
    expect(_catalog_card(scoped_user_page, "Kubernetes namespace")).to_have_count(1)
    expect(_catalog_card(scoped_user_page, "Databases")).to_have_count(1)

    _open_portfolio(scoped_user_page, "Databases")
    expect(_catalog_card(scoped_user_page, "PostgreSQL database")).to_have_count(1)
    expect(_catalog_card(scoped_user_page, "PostgreSQL database").get_by_role("link", name="Order")).to_be_visible()


def test_admin_browses_the_same_catalog_and_the_service_list(admin_page):
    goto_sidebar_entry(admin_page, "Service catalog")
    expect(_catalog_card(admin_page, "Infrastructure")).to_have_count(1)

    admin_page.get_by_role("link", name="All services").click()
    for service_name in ["Virtual machine", "Kubernetes namespace", "PostgreSQL database"]:
        expect_table_contains(admin_page, service_name)


def test_scoped_user_requests_a_virtual_machine_end_to_end(scoped_user_page):
    """The critical path: catalog -> wizard -> a SUBMITTED request and a new instance."""
    instance_name = _unique("vm")
    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, "Infrastructure")
    _order_service(scoped_user_page, "Virtual machine")

    _fill_first_step(scoped_user_page, instance_name, "SRE")
    expect(scoped_user_page.locator("form")).to_contain_text("vCPU")
    _fill_survey_step(scoped_user_page, vcpu=4, memory=16, environment="staging")
    _submit_wizard_step(scoped_user_page)

    expect(scoped_user_page).to_have_url(re.compile(r"/service-catalog/request/$"))
    request_row = table_row(scoped_user_page, instance_name)
    expect(request_row).to_have_count(1)
    expect(request_row).to_contain_text("SUBMITTED")

    request_row.locator("a:visible").first.click()
    scoped_user_page.wait_for_load_state()
    details = scoped_user_page.locator(".card-body").first
    expect(details).to_contain_text("SUBMITTED")
    expect(details).to_contain_text(instance_name)
    survey = scoped_user_page.locator(".timeline")
    for answer in ["vcpu", "4", "memory", "16", "environment", "staging"]:
        expect(survey).to_contain_text(answer)

    goto_sidebar_entry(scoped_user_page, "Instances")
    expect_table_contains(scoped_user_page, instance_name)


def test_survey_refuses_a_vcpu_above_the_maximum(scoped_user_page):
    """64 vCPU is the maximum of the seeded survey: 999 keeps the user on the survey step."""
    instance_name = _unique("too-big")
    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, "Infrastructure")
    _order_service(scoped_user_page, "Virtual machine")
    _fill_first_step(scoped_user_page, instance_name, "SRE")

    _fill_survey_step(scoped_user_page, vcpu=999, memory=16, environment="dev")
    _submit_wizard_step(scoped_user_page)

    vcpu_field = scoped_user_page.locator("input[name='1-vcpu']")
    expect(vcpu_field).to_be_visible()
    assert vcpu_field.evaluate("field => field.validationMessage") != "", \
        "999 vCPU was accepted: the survey maximum is not enforced on the request form"

    goto_sidebar_entry(scoped_user_page, "Requests")
    expect(scoped_user_page.locator("table.table")).to_be_visible()
    expect_table_does_not_contain(scoped_user_page, instance_name)


def test_the_instance_name_is_required_on_the_first_wizard_step(scoped_user_page):
    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, "Infrastructure")
    _order_service(scoped_user_page, "Virtual machine")

    _submit_wizard_step(scoped_user_page)

    name_field = scoped_user_page.locator("input[name='0-name']")
    expect(name_field).to_be_visible()
    assert name_field.evaluate("field => field.validationMessage") != "", \
        "the wizard accepted an instance without a name"


def test_the_quota_scope_choice_is_limited_to_the_scopes_of_the_user(scoped_user_page, login_as):
    """bob belongs to an organization and to one of its teams, and to nothing of Marketing."""
    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, "Infrastructure")
    _order_service(scoped_user_page, "Virtual machine")

    bob_scopes = _option_labels(scoped_user_page, "0-quota_scope")
    assert "Platform Engineering" in bob_scopes, bob_scopes
    assert any(scope.endswith(" - SRE") for scope in bob_scopes), bob_scopes
    for foreign_scope in ["Marketing", "Web"]:
        assert not any(scope.endswith(f" - {foreign_scope}") for scope in bob_scopes), \
            f"bob was offered the '{foreign_scope}' scope: {bob_scopes}"

    carol_page = login_as("carol")
    goto_sidebar_entry(carol_page, "Service catalog")
    _open_portfolio(carol_page, "Infrastructure")
    _order_service(carol_page, "Virtual machine")
    carol_scopes = _option_labels(carol_page, "0-quota_scope")
    assert any(scope.endswith(" - Web") for scope in carol_scopes), carol_scopes
    assert not any(scope.endswith(" - SRE") for scope in carol_scopes), carol_scopes


def test_a_request_of_another_scope_is_hidden_and_answers_403(scoped_user_page, login_as):
    """carol's Marketing request is invisible to bob, and its page is refused."""
    carol_page = login_as("carol")
    goto_sidebar_entry(carol_page, "Requests")
    table_row(carol_page, "campaign-site").locator("a:visible").first.click()
    carol_page.wait_for_load_state()
    carol_request_url = carol_page.url

    goto_sidebar_entry(scoped_user_page, "Requests")
    expect(scoped_user_page.locator("table.table")).to_be_visible()
    expect_table_does_not_contain(scoped_user_page, "campaign-site")
    response = scoped_user_page.goto(carol_request_url)
    assert response.status == 403, f"bob got {response.status} on a Marketing request"


def test_admin_publishes_a_new_service_and_a_user_can_request_it(admin_page, scoped_user_page):
    """Portfolio, service and create operation created through the UI make the service requestable."""
    portfolio_name, service_name, operation_name = _create_requestable_service(admin_page)
    expect(admin_page.locator("body")).to_contain_text(operation_name)

    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, portfolio_name)
    expect(_catalog_card(scoped_user_page, service_name)).to_have_count(1)

    instance_name = _unique("published")
    _order_service(scoped_user_page, service_name)
    _fill_first_step(scoped_user_page, instance_name, "SRE")
    _fill_survey_step(scoped_user_page, vcpu=2, memory=8, environment="dev")
    _submit_wizard_step(scoped_user_page)

    request_row = table_row(scoped_user_page, instance_name)
    expect(request_row).to_have_count(1)
    expect(request_row).to_contain_text(service_name)
    expect(request_row).to_contain_text("SUBMITTED")


def test_disabling_a_field_of_the_survey_removes_it_from_the_request_form(admin_page, scoped_user_page):
    """A field that is not a customer field must not be asked to the requester any more."""
    portfolio_name, service_name, _ = _create_requestable_service(admin_page)
    admin_page.get_by_role("link", name="Survey").first.click()
    admin_page.wait_for_load_state()
    vcpu_card = admin_page.locator("div.card:has(h3.card-title strong:text-is('vcpu'))")
    vcpu_card.locator("input[type='checkbox'][name$='is_customer_field']").uncheck()
    admin_page.get_by_role("button", name="Update survey").click()
    admin_page.wait_for_load_state()

    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, portfolio_name)
    _order_service(scoped_user_page, service_name)
    _fill_first_step(scoped_user_page, _unique("no-vcpu"), "SRE")

    expect(scoped_user_page.locator("form")).to_contain_text("Memory (GB)")
    expect(scoped_user_page.locator("input[name='1-vcpu']")).to_have_count(0)


def test_a_disabled_service_is_not_requestable_by_a_user(admin_page, scoped_user_page):
    portfolio_name, service_name, _ = _create_requestable_service(admin_page)
    _open_service(admin_page, service_name)
    service_edit_path = f"{urlparse(admin_page.url).path.rstrip('/')}/edit/"
    admin_page.locator(f"a[href='{service_edit_path}']").click()
    admin_page.wait_for_load_state()
    admin_page.locator("input[name='enabled']").uncheck()
    submit_form(admin_page)

    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, portfolio_name)
    expect(_catalog_card(scoped_user_page, service_name)).to_have_count(0)


def test_a_service_without_a_create_operation_is_not_in_the_catalog(admin_page, scoped_user_page):
    portfolio_name = _unique("Empty portfolio")
    service_name = _unique("Service without operation")
    _create_portfolio(admin_page, portfolio_name)
    _create_service(admin_page, service_name, portfolio_name)

    goto_sidebar_entry(scoped_user_page, "Service catalog")
    _open_portfolio(scoped_user_page, portfolio_name)
    expect(_catalog_card(scoped_user_page, service_name)).to_have_count(0)


def test_the_doc_list_renders_and_a_doc_opens(admin_page, scoped_user_page):
    """Docs are written in the Django admin, and read by everybody from the 'Docs' sidebar entry."""
    title = _unique("Runbook")
    content = f"How to consume the catalog {title}"
    goto_sidebar_entry(admin_page, "Docs")
    admin_page.get_by_role("link", name="Manage docs").click()
    admin_page.wait_for_load_state()
    admin_page.get_by_role("link", name=re.compile("Add doc", re.IGNORECASE)).first.click()
    admin_page.fill("input[name='title']", title)
    editor_input = admin_page.locator("textarea.ace_text-input").first
    editor_input.click(force=True)
    editor_input.press_sequentially(content)
    admin_page.get_by_role("button", name="Save", exact=True).click()
    admin_page.wait_for_load_state()

    goto_sidebar_entry(scoped_user_page, "Docs")
    expect_table_contains(scoped_user_page, title)
    table_row(scoped_user_page, title).get_by_role("link").first.click()
    scoped_user_page.wait_for_load_state()
    expect(scoped_user_page.locator("body")).to_contain_text(content)
