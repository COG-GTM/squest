"""Instances, day 2 operations and support: what a user does with what they already own.

The flows here start from the "Instances" and "Support" sidebar entries: reading an instance, asking
for a day 2 operation on it, renaming and deleting it, and opening, commenting, closing and
reopening a support ticket. Every flow is walked as the scoped non admin (``bob``) wherever a normal
user is allowed to, and the scope boundary is asserted from the other side (``carol``, in Marketing).

Two things the seed cannot give this spec, both reported in the pull request:

* an instance can only be created through the catalog request wizard, so the tests that need a
  throw away instance (rename, delete, bulk delete) build one with ``_order_new_instance``. The
  wizard itself is another spec's flow family: here it is setup, not coverage.
* ``Instance.archive`` only accepts the DELETED state and the demo catalog has no DELETE operation,
  so no instance can be walked into the archived list through the user interface. The round trip is
  therefore replaced by what is reachable: the archived list itself, and the archive button and URL
  being refused on an instance that was never deleted.
"""
import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from e2e.helpers import goto_sidebar_entry, submit_form

SEEDED_SUPPORTS = ["Disk usage above 90%", "Cannot reach the instance over SSH",
                   "Please increase the connection limit"]


def _unique(prefix: str) -> str:
    """A name no other test and no previous run against a kept database can collide with."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _rows(page: Page, table_id: str, text: str):
    """A row of one named table. The instance detail page renders three tables at once."""
    return page.locator(f"#{table_id} tbody tr").filter(has_text=text)


def _apply_filter(page: Page, field: str, value: str) -> None:
    page.wait_for_load_state("load")
    filter_field = page.locator(f"input[name='{field}']")
    opener = page.locator(".content-header a[data-widget='control-sidebar']")
    expect(opener).to_have_count(1)
    for _ in range(3):
        if filter_field.is_visible():
            break
        if page.locator("body.control-sidebar-open, body.control-sidebar-slide-open").count():
            expect(filter_field).to_be_visible(timeout=1000)
            break
        opener.click()
        expect(page.locator("body")).to_have_class(
            re.compile(r"(^|\s)control-sidebar-(?:open|slide-open)(\s|$)"), timeout=1000
        )
    expect(filter_field).to_be_visible(timeout=1000)
    filter_field.fill(value)
    with page.expect_navigation():
        page.get_by_role("button", name="Apply").click()
    page.wait_for_load_state()


def _instance_rows(page: Page, name: str):
    goto_sidebar_entry(page, "Instances")
    _apply_filter(page, "name", name)
    return _rows(page, "instance_table", name)


def _support_rows(page: Page, title: str):
    goto_sidebar_entry(page, "Support")
    _apply_filter(page, "title", title)
    return _rows(page, "support_table", title)


def _open_instance(page: Page, name: str) -> None:
    """Instances sidebar entry, then the instance's own link in the list."""
    _instance_rows(page, name).get_by_role("link", name=name, exact=True).click()
    page.wait_for_load_state()


def _open_tab(page: Page, name: str) -> None:
    page.locator("#tabs").get_by_role("link", name=name, exact=True).click()


def _instance_url(page: Page, name: str) -> str:
    """The URL of an instance, read from a list the given page is allowed to see.

    Used to hand another user a page they must not be able to open: a 403 can only be asserted on a
    URL, and this keeps the URL the one Squest itself renders.
    """
    return _instance_rows(page, name).get_by_role("link", name=name, exact=True).get_attribute("href")


def _detail_field(page: Page, label: str):
    """One entry of the instance detail summary card, e.g. 'State' or 'Quota scope'."""
    return page.locator("li.list-group-item").filter(has_text=re.compile(rf"^\s*{label}\b"))


def _order_new_instance(admin_page: Page, name: str) -> None:
    """Walks the catalog wizard to get an instance of our own. Setup only, not coverage."""
    goto_sidebar_entry(admin_page, "Service catalog")
    admin_page.locator(".card", has_text="Infrastructure").get_by_role("link", name="Open").first.click()
    admin_page.locator(".card", has_text="Provision a RHEL virtual machine").get_by_role(
        "link", name="Order").first.click()
    if re.search(r"/operation/request/$", admin_page.url):
        _rows(admin_page, "operation_table", "Create virtual machine").get_by_role("link").first.click()

    admin_page.fill("input[name='0-name']", name)
    admin_page.select_option("select[name='0-quota_scope']", label="Platform Engineering")
    admin_page.locator("input[type='submit']").click()
    admin_page.fill("input[name='1-vcpu']", "2")
    admin_page.fill("input[name='1-memory']", "8")
    admin_page.locator("input[type='submit']").click()
    expect(admin_page).to_have_url(re.compile(r"/service-catalog/request/$"))


def _open_new_support(page: Page, instance_name: str, title: str) -> None:
    """Opens a support ticket from the instance the user owns."""
    _open_instance(page, instance_name)
    page.get_by_role("link", name="Open new support").click()
    page.fill("input[name='title']", title)
    page.fill("textarea[name='content']", f"Opened by the end to end suite: {title}")
    submit_form(page)


def _comment_support(page: Page, content: str) -> None:
    page.fill("textarea[name='content']", content)
    page.get_by_role("button", name="Comment").click()
    page.wait_for_load_state()


# ---------------------------------------------------------------------------- instance list/detail


def test_admin_reads_the_instance_list_columns(admin_page):
    row = _instance_rows(admin_page, "batch-worker-01")
    expect(row).to_have_count(1)
    expect(row).to_contain_text("Virtual machine")
    expect(row).to_contain_text("SRE")
    expect(row).to_contain_text("AVAILABLE")
    expect(row).to_contain_text("bob")
    # the whole demo estate, both organizations included, is visible to a superuser
    for name in ["web-frontend-01", "web-frontend-02", "analytics-ns", "reporting-db", "campaign-site"]:
        expect(_instance_rows(admin_page, name)).to_have_count(1)


def test_admin_reads_an_instance_detail_page(admin_page):
    _open_instance(admin_page, "batch-worker-01")
    expect(admin_page.locator(".card-title").first).to_contain_text("batch-worker-01")
    expect(_detail_field(admin_page, "State")).to_contain_text("AVAILABLE")
    expect(_detail_field(admin_page, "Service")).to_contain_text("Virtual machine")
    expect(_detail_field(admin_page, "Quota scope")).to_contain_text("Platform Engineering - SRE")
    expect(_detail_field(admin_page, "Owner")).to_contain_text("bob")
    # the tracked resource of the instance, shown to a user allowed to change it
    expect(_detail_field(admin_page, "Resources")).to_contain_text("batch-worker-01")

    _open_tab(admin_page, "Specs")
    expect(admin_page.locator("#spec")).to_contain_text("User spec")
    expect(admin_page.locator("#spec")).to_contain_text("Admin spec")

    _open_tab(admin_page, "Requests")
    expect(_rows(admin_page, "request_table", "Create virtual machine")).to_have_count(1)

    _open_tab(admin_page, "Support")
    expect(_rows(admin_page, "support_table", "Cannot reach the instance over SSH")).to_have_count(1)


def test_scoped_user_reads_their_own_instance_without_the_admin_spec(scoped_user_page):
    """bob sees his organization's instances, but the admin spec stays hidden from him."""
    for name in ["batch-worker-01", "web-frontend-01", "reporting-db"]:
        expect(_instance_rows(scoped_user_page, name)).to_have_count(1)
    expect(_instance_rows(scoped_user_page, "campaign-site")).to_have_count(0)

    _open_instance(scoped_user_page, "batch-worker-01")
    expect(_detail_field(scoped_user_page, "State")).to_contain_text("AVAILABLE")
    expect(_detail_field(scoped_user_page, "Owner")).to_contain_text("bob")
    _open_tab(scoped_user_page, "Specs")
    expect(scoped_user_page.locator("#spec")).to_contain_text("User spec")
    expect(scoped_user_page.locator("#spec")).not_to_contain_text("Admin spec")


def test_another_scopes_instance_is_hidden_and_answers_403(admin_page, scoped_user_page):
    campaign_site = _instance_url(admin_page, "campaign-site")
    response = scoped_user_page.goto(campaign_site)
    assert response.status == 403, f"bob got {response.status} on an instance of the Marketing scope"


# --------------------------------------------------------------------------- day 2 operation


def test_scoped_user_requests_a_resize_on_the_instance_they_own(scoped_user_page):
    comment = _unique("resize requested by the e2e suite")
    _open_instance(scoped_user_page, "batch-worker-01")
    _open_tab(scoped_user_page, "Requests")
    requests_before = _rows(scoped_user_page, "request_table", "Resize virtual machine").count()

    _open_tab(scoped_user_page, "Operations")
    resize = _rows(scoped_user_page, "operation_table", "Resize virtual machine")
    expect(resize).to_have_count(1)
    resize.get_by_role("link").last.click()

    scoped_user_page.fill("input[name='vcpu']", "16")
    scoped_user_page.fill("input[name='memory']", "64")
    scoped_user_page.select_option("select[name='environment']", "prod")
    scoped_user_page.fill("textarea[name='request_comment']", comment)
    submit_form(scoped_user_page, "Request the operation")

    # Squest lands the requester on their request list, with the new request on it
    expect(scoped_user_page).to_have_url(re.compile(r"/service-catalog/request/$"))
    expect(_rows(scoped_user_page, "request_table", "Resize virtual machine").first).to_contain_text("batch-worker-01")

    _open_instance(scoped_user_page, "batch-worker-01")
    _open_tab(scoped_user_page, "Requests")
    expect(_rows(scoped_user_page, "request_table", "Resize virtual machine")).to_have_count(requests_before + 1)


def test_day_two_operation_is_not_offered_on_an_instance_that_is_not_available(scoped_user_page):
    """reporting-db is PENDING: its resize operation exists but Squest refuses to offer it."""
    _open_instance(scoped_user_page, "reporting-db")
    expect(_detail_field(scoped_user_page, "State")).to_contain_text("PENDING")
    _open_tab(scoped_user_page, "Operations")
    expect(scoped_user_page.locator("#operations")).to_contain_text("Instance not available")
    expect(scoped_user_page.locator("#operations").get_by_role("link")).to_have_count(0)


@pytest.mark.xfail(reason="Squest gates the day 2 operation URL on the operation's own permission "
                          "(view_operation, granted at global scope) and never on the instance, so a user "
                          "of another scope reaches the survey of an instance they cannot even display. "
                          "Reported to the harness owner.")
def test_day_two_operation_of_another_scope_answers_403(admin_page, login_as):
    carol_page = login_as("carol")
    _open_instance(admin_page, "batch-worker-01")
    _open_tab(admin_page, "Operations")
    resize_url = _rows(admin_page, "operation_table", "Resize virtual machine").get_by_role(
        "link").last.get_attribute("href")
    response = carol_page.goto(resize_url)
    assert response.status == 403, f"carol got {response.status} on a day 2 operation of the Platform scope"


# --------------------------------------------------------------------------- edit, archive, delete


def test_admin_renames_an_instance(admin_page):
    name = _unique("e2e-rename")
    renamed = _unique("e2e-renamed")
    _order_new_instance(admin_page, name)

    _open_instance(admin_page, name)
    admin_page.locator("a.btn-primary[href$='/edit/']").first.click()
    admin_page.fill("input[name='name']", renamed)
    submit_form(admin_page, "Update")

    expect(admin_page.locator(".card-title").first).to_contain_text(renamed)
    expect(_instance_rows(admin_page, renamed)).to_have_count(1)
    expect(_instance_rows(admin_page, name)).to_have_count(0)

    _open_instance(admin_page, renamed)
    admin_page.locator("a.btn-danger[href$='/delete/']").first.click()
    expect(admin_page.locator(".card-title").first).to_contain_text(f"Confirm deletion of {renamed}")
    admin_page.get_by_role("button", name="Confirm").click()
    admin_page.wait_for_load_state()
    expect(admin_page).to_have_url(re.compile(r"/instance/$"))
    expect(_instance_rows(admin_page, renamed)).to_have_count(0)


def test_archiving_is_refused_on_an_instance_that_was_never_deleted(admin_page):
    """``Instance.archive`` only leaves the DELETED state, so an AVAILABLE instance offers no button."""
    _open_instance(admin_page, "batch-worker-01")
    expect(admin_page.get_by_title("Archive")).to_have_count(0)
    expect(admin_page.get_by_title("Unarchive")).to_have_count(0)

    instance_url = _instance_url(admin_page, "batch-worker-01")
    response = admin_page.goto(instance_url.rstrip("/") + "/archive/")
    assert response.status == 403, f"archiving an AVAILABLE instance answered {response.status}"


def test_the_archived_instance_list_is_reachable_and_holds_no_live_instance(admin_page):
    goto_sidebar_entry(admin_page, "Instances")
    admin_page.get_by_role("link", name="Archived instances").click()
    expect(admin_page.locator(".breadcrumb")).to_contain_text("Archived instance")
    expect(_rows(admin_page, "instance_table", "batch-worker-01")).to_have_count(0)


def test_admin_deletes_an_instance_through_the_confirmation_page(admin_page):
    name = _unique("e2e-delete")
    _order_new_instance(admin_page, name)

    _open_instance(admin_page, name)
    admin_page.locator("a.btn-danger[href$='/delete/']").first.click()
    expect(admin_page.locator(".card-title").first).to_contain_text(f"Confirm deletion of {name}")
    admin_page.get_by_role("button", name="Confirm").click()
    admin_page.wait_for_load_state()

    expect(admin_page).to_have_url(re.compile(r"/instance/$"))
    expect(_instance_rows(admin_page, name)).to_have_count(0)


def test_admin_bulk_deletes_instances_from_the_list_checkboxes(admin_page):
    first = _unique("e2e-bulk")
    second = _unique("e2e-bulk")
    _order_new_instance(admin_page, first)
    _order_new_instance(admin_page, second)

    goto_sidebar_entry(admin_page, "Instances")
    _apply_filter(admin_page, "name", "e2e-bulk-")
    for name in [first, second]:
        row = _rows(admin_page, "instance_table", name)
        expect(row).to_have_count(1)
        row.locator("input[name='selection']").check()
    admin_page.get_by_role("button", name="Delete").click()
    admin_page.wait_for_load_state()

    confirmation = admin_page.locator(".card-danger")
    expect(confirmation).to_contain_text(first)
    expect(confirmation).to_contain_text(second)
    confirmation.get_by_role("button", name="Delete").click()
    admin_page.wait_for_load_state()

    expect(admin_page).to_have_url(re.compile(r"/instance/$"))
    expect(_rows(admin_page, "instance_table", first)).to_have_count(0)
    expect(_rows(admin_page, "instance_table", second)).to_have_count(0)


def test_scoped_user_cannot_delete_an_instance(scoped_user_page):
    goto_sidebar_entry(scoped_user_page, "Instances")
    # no bulk delete button and no selection column without the delete permission
    expect(scoped_user_page.get_by_role("button", name="Delete")).to_have_count(0)
    expect(scoped_user_page.locator("input[name='selection']")).to_have_count(0)

    instance_url = _instance_url(scoped_user_page, "batch-worker-01")
    scoped_user_page.goto(instance_url)
    expect(scoped_user_page.locator("a.btn-danger")).to_have_count(0)
    response = scoped_user_page.goto(instance_url.rstrip("/") + "/delete/")
    assert response.status == 403, f"bob got {response.status} on the delete page of an instance"


# --------------------------------------------------------------------------- support


def test_support_list_holds_the_seeded_tickets_and_stays_in_scope(admin_page, scoped_user_page, login_as):
    for title in SEEDED_SUPPORTS:
        row = _support_rows(admin_page, title)
        expect(row).to_have_count(1)
        expect(row).to_contain_text("OPENED")

    for title in SEEDED_SUPPORTS:
        expect(_support_rows(scoped_user_page, title)).to_have_count(1)

    # every seeded ticket belongs to the Platform Engineering scope: carol must see none of them
    carol_page = login_as("carol")
    goto_sidebar_entry(carol_page, "Support")
    expect(carol_page.get_by_role("heading", name="Support")).to_be_visible()
    for title in SEEDED_SUPPORTS:
        expect(_support_rows(carol_page, title)).to_have_count(0)


def test_owner_opens_a_support_ticket_and_the_admin_answers_it(scoped_user_page, admin_page):
    title = _unique("e2e-support")
    _open_new_support(scoped_user_page, "batch-worker-01", title)

    # Squest sends the owner back to the support tab of the instance, with the new ticket on it
    # (that table is rendered without pagination, so the new row is always on it)
    expect(_rows(scoped_user_page, "support_table", title)).to_have_count(1)

    _support_rows(scoped_user_page, title).get_by_role("link", name=re.compile(title)).click()
    expect(scoped_user_page.get_by_title("state")).to_contain_text("OPENED")
    _comment_support(scoped_user_page, "bob: still reproducing after a reboot")
    expect(scoped_user_page.locator(".post").last).to_contain_text("bob: still reproducing after a reboot")

    _support_rows(admin_page, title).get_by_role("link", name=re.compile(title)).click()
    expect(admin_page.locator(".post").first).to_contain_text("bob")
    _comment_support(admin_page, "admin: a maintenance window is scheduled")

    scoped_user_page.reload()
    expect(scoped_user_page.locator(".post").last).to_contain_text("admin: a maintenance window is scheduled")


def test_admin_closes_and_reopens_a_support_ticket(scoped_user_page, admin_page):
    title = _unique("e2e-close")
    _open_new_support(scoped_user_page, "batch-worker-01", title)
    # the "Squest user" role holds no close_support permission: the owner is not offered the button
    _support_rows(scoped_user_page, title).get_by_role("link", name=re.compile(title)).click()
    expect(scoped_user_page.get_by_title("state")).to_contain_text("OPENED")
    expect(scoped_user_page.get_by_role("link", name="Close")).to_have_count(0)

    _support_rows(admin_page, title).get_by_role("link", name=re.compile(title)).click()
    admin_page.get_by_role("link", name="Close").click()
    expect(admin_page.get_by_title("state")).to_contain_text("CLOSED")

    expect(_support_rows(admin_page, title)).to_contain_text("CLOSED")

    _support_rows(admin_page, title).get_by_role("link", name=re.compile(title)).click()
    admin_page.get_by_role("link", name="Re-open").click()
    expect(admin_page.get_by_title("state")).to_contain_text("OPENED")
    expect(_support_rows(admin_page, title)).to_contain_text("OPENED")


def test_a_support_ticket_of_another_scope_answers_403(scoped_user_page, login_as):
    title = _unique("e2e-scope")
    _open_new_support(scoped_user_page, "batch-worker-01", title)
    support_url = _support_rows(scoped_user_page, title).get_by_role(
        "link", name=re.compile(title)).get_attribute("href")

    carol_page = login_as("carol")
    response = carol_page.goto(support_url)
    assert response.status == 403, f"carol got {response.status} on a support of the Platform Engineering scope"
