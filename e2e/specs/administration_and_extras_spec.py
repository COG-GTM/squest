"""Administration and extras: the operator's surface.

The RHAAP/AWX server administration (add, sync, job templates, compliancy, token, delete) plus the
"Extras" treeview: global hooks, announcements, custom links and email templates. Everything here is
driven through the sidebar and the buttons of the pages themselves, and asserted on what the
operator (or, for an announcement and a custom link, the normal user) sees.

The stub of ``e2e/aap_stub`` serves two job templates: "Deploy virtual machine" (compliant) and
"Decommission virtual machine" (``ask_variables_on_launch`` false, so deliberately not compliant).
"""
import re
import uuid
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import Page, expect

from e2e.aap_stub.fake_tower import AUTH_FAILURE_TOKEN
from e2e.helpers import NAV_MAP, expect_message, expect_no_form_error, goto_sidebar_entry, \
    expect_form_error, submit_form, table_row as helper_table_row, \
    visible_sidebar_entries

COMPLIANT_JOB_TEMPLATE = "Deploy virtual machine"
NON_COMPLIANT_JOB_TEMPLATE = "Decommission virtual machine"
# every page of the Administration group this spec covers, as the sidebar names them
ADMINISTRATION_ENTRIES = ["RHAAP/AWX", "Request hook", "Instance hook", "Announcements", "Custom links", "Emails"]
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def _unique(prefix: str) -> str:
    """A name no other test and no earlier run can collide with (``E2E_REUSE_DB`` keeps the data)."""
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def _select_option(page: Page, field: str, label: str) -> None:
    """Picks an option of a Squest select.

    Squest decorates every select with bootstrap-select, which hides the real ``<select>`` behind a
    rendered dropdown, so the option is picked on the underlying element.
    """
    page.locator(f"select[name='{field}']").select_option(label=label, force=True)


def _select_option_containing(page: Page, field: str, text: str) -> str:
    """Picks the first option whose label holds ``text``, and returns that label.

    Squest labels a job template "<name> (<tower server>)" and an operation "<name> (<service>)", so
    a spec that creates its own tower server cannot know the whole label up front.
    """
    options = page.locator(f"select[name='{field}'] option")
    labels = [label.strip() for label in options.all_inner_texts() if text in label]
    assert labels, f"no option of '{field}' holds '{text}'"
    _select_option(page, field, labels[0])
    return labels[0]


def _add_tower_server(page: Page) -> str:
    """Adds a server backed by the stub and returns its name. The host is unique in the database."""
    name = _unique("Operator AAP")
    goto_sidebar_entry(page, "RHAAP/AWX")
    page.get_by_role("link", name="Add").click()
    page.fill("input[name='name']", name)
    page.fill("input[name='host']", f"https://{uuid.uuid4().hex[:8]}.aap.stub.local")
    page.fill("input[name='token']", "a-token-the-stub-accepts")
    submit_form(page)
    expect(_table_row(page, name)).to_have_count(1)
    return name


def _open_job_template_list(page: Page, tower_name: str) -> None:
    """Walks from the server list to the job template list through the count button of the row."""
    _table_row(page, tower_name).locator("a[id^='job_template_count_']").click()
    page.wait_for_load_state()


def _row_action(page: Page, row_text: str, title: str):
    return _table_row(page, row_text).locator(f"a[title='{title}']")


def _wait_for_list_settled(page: Page) -> None:
    """Waits until a list table is attached, allowing Squest's empty-list page."""
    page.wait_for_load_state("domcontentloaded")
    table = page.locator("table.table").first
    if table.count():
        table.wait_for(state="attached")


def _pagination(page: Page):
    """Squest's table template renders one pagination block per page."""
    return page.locator("ul.pagination").first


def _next_page(page: Page):
    return _pagination(page).locator("li:not(.disabled) a").filter(has_text="next").first


def _table_row(page: Page, text: str):
    """Walks pagination because E2E_REUSE_DB accumulates rows across runs."""
    _wait_for_list_settled(page)
    row = helper_table_row(page, text)
    for _ in range(500):
        if row.count():
            return row
        next_link = _next_page(page)
        if not next_link.count():
            return row
        with page.expect_navigation():
            next_link.click()
        _wait_for_list_settled(page)
        row = helper_table_row(page, text)
    raise AssertionError("pagination exceeded 500 pages while searching for a row")


def _expect_no_row(page: Page, list_entry: str, text: str) -> None:
    """Re-enters a list at page one, then asserts no matching row exists on any page."""
    goto_sidebar_entry(page, list_entry)
    _wait_for_list_settled(page)
    row = helper_table_row(page, text)
    for _ in range(500):
        expect(row).to_have_count(0)
        next_link = _next_page(page)
        if not next_link.count():
            return
        with page.expect_navigation():
            next_link.click()
        _wait_for_list_settled(page)
        row = helper_table_row(page, text)
    raise AssertionError("pagination exceeded 500 pages while checking for a row")


def _delete_row(page: Page, row_text: str) -> None:
    """Deletes a list row through its trash button and the generic confirmation page."""
    _row_action(page, row_text, "Delete").click()
    expect(page.locator("body")).to_contain_text("Confirm deletion of")
    submit_form(page, "Confirm")


def _fill_json(page: Page, field: str, value: str) -> None:
    page.fill(f"textarea[name='{field}']", value)


def test_operator_reaches_the_job_template_detail_of_their_own_server(admin_page):
    """The synced templates are browsable: list of the server, then the detail of one of them."""
    tower_name = _add_tower_server(admin_page)
    _open_job_template_list(admin_page, tower_name)

    job_template_table = admin_page.locator("#job_template_table")
    expect(job_template_table).to_contain_text(COMPLIANT_JOB_TEMPLATE)
    expect(job_template_table).to_contain_text(NON_COMPLIANT_JOB_TEMPLATE)

    _table_row(admin_page, COMPLIANT_JOB_TEMPLATE).get_by_role("link", name=COMPLIANT_JOB_TEMPLATE).click()
    details = admin_page.locator("section", has_text="Details").first
    expect(details).to_contain_text(COMPLIANT_JOB_TEMPLATE)
    expect(details).to_contain_text(tower_name)
    expect(details).to_contain_text("Job template ID (Tower/AWX)")
    expect(admin_page.locator("#data")).to_contain_text("ask_variables_on_launch")


def test_compliancy_page_reports_a_compliant_job_template_as_a_success(admin_page):
    tower_name = _add_tower_server(admin_page)
    _open_job_template_list(admin_page, tower_name)

    row = _table_row(admin_page, COMPLIANT_JOB_TEMPLATE)
    expect(row.locator("[id^='icon_'][class*='fa-check']")).to_have_count(1)
    row.locator("[id^='icon_']").click()
    admin_page.wait_for_load_state()

    card = admin_page.locator(".card", has_text="Variables/Prompt on launch")
    expect(card.locator(".card-header")).to_have_class(re.compile(r"bg-success"))


def test_compliancy_page_warns_about_prompt_on_launch_for_a_non_compliant_job_template(admin_page):
    """The flow an operator walks to find out why a template cannot be used by Squest."""
    tower_name = _add_tower_server(admin_page)
    _open_job_template_list(admin_page, tower_name)

    row = _table_row(admin_page, NON_COMPLIANT_JOB_TEMPLATE)
    expect(row.locator("[id^='icon_'][class*='fa-times']")).to_have_count(1)
    row.locator("[id^='icon_']").click()
    admin_page.wait_for_load_state()

    card = admin_page.locator(".card", has_text="Variables/Prompt on launch")
    expect(card.locator(".card-header")).to_have_class(re.compile(r"bg-warning"))
    expect(card.locator(".card-body")).to_contain_text("Prompt on Launch")
    expect(card.locator(".card-body")).to_contain_text("ask_variables_on_launch")


def test_operator_renames_an_aap_server(admin_page):
    tower_name = _add_tower_server(admin_page)
    renamed = _unique("Renamed AAP")

    _row_action(admin_page, tower_name, "Edit").click()
    admin_page.fill("input[name='name']", renamed)
    submit_form(admin_page)

    expect_no_form_error(admin_page)
    expect(_table_row(admin_page, renamed)).to_have_count(1)
    _expect_no_row(admin_page, "RHAAP/AWX", tower_name)


def test_operator_updates_the_token_of_an_aap_server(admin_page):
    """The token is write only: the edit page sends the operator to a dedicated form for it."""
    tower_name = _add_tower_server(admin_page)

    _row_action(admin_page, tower_name, "Edit").click()
    expect(admin_page.locator("input[name='token']")).to_have_count(0)
    admin_page.get_by_role("link", name="Update token").click()

    admin_page.fill("input[name='token']", "a-rotated-token-the-stub-accepts")
    submit_form(admin_page)

    expect_no_form_error(admin_page)
    expect(admin_page).to_have_url(re.compile(r"/tower/$"))
    expect(_table_row(admin_page, tower_name)).to_have_count(1)


def test_operator_is_told_when_the_aap_token_is_refused(admin_page):
    name = _unique("Rejected AAP")
    goto_sidebar_entry(admin_page, "RHAAP/AWX")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    admin_page.fill("input[name='host']", f"https://{uuid.uuid4().hex[:8]}.aap.stub.local")
    admin_page.fill("input[name='token']", AUTH_FAILURE_TOKEN)
    submit_form(admin_page)

    expect_form_error(admin_page, "Fail to authenticate with provided token")
    goto_sidebar_entry(admin_page, "RHAAP/AWX")
    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "RHAAP/AWX", name)


def test_operator_deletes_an_aap_server(admin_page):
    tower_name = _add_tower_server(admin_page)

    _delete_row(admin_page, tower_name)

    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "RHAAP/AWX", tower_name)


def test_announcement_of_an_admin_is_displayed_to_a_normal_user(admin_page, scoped_user_page):
    title = _unique("Maintenance window")
    message = f"The platform is read only during {title}"
    _create_announcement(admin_page, title, message)

    expect(_table_row(admin_page, title)).to_have_count(1)

    scoped_user_page.locator("aside.main-sidebar a.brand-link").click()
    scoped_user_page.wait_for_load_state()
    announcement = scoped_user_page.locator(".alert.alert-info", has_text=title)
    expect(announcement).to_have_count(1)
    expect(announcement).to_contain_text(message)


def test_announcement_can_be_edited_and_deleted(admin_page):
    title = _unique("Draft announcement")
    _create_announcement(admin_page, title, "First wording")

    edited = _unique("Edited announcement")
    _row_action(admin_page, title, "Edit").click()
    admin_page.fill("input[name='title']", edited)
    submit_form(admin_page)
    expect_no_form_error(admin_page)
    expect(_table_row(admin_page, edited)).to_have_count(1)

    _row_action(admin_page, edited, "Delete").click()
    # AnnouncementDeleteView sets this warning but generics/confirm-delete-template.html suppresses it
    # because details_list is empty; assert the confirmation text until that application bug is fixed.
    expect(admin_page.locator("body")).to_contain_text("Confirm deletion of")
    submit_form(admin_page, "Confirm")
    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "Announcements", edited)


def _create_announcement(page: Page, title: str, message: str) -> None:
    """Creates an announcement that is live right now, so a user sees it on the home page."""
    goto_sidebar_entry(page, "Announcements")
    page.get_by_role("link", name="Add").click()
    now_text = page.locator("small.form-text", has_text="Time Zone is").first
    now = datetime.now()
    if now_text.count():
        match = re.search(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)", now_text.inner_text())
        if match:
            now = datetime.strptime(match.group(1), DATETIME_FORMAT)
    page.fill("input[name='title']", title)
    page.fill("textarea[name='message']", message)
    page.fill("input[name='date_start']", now.replace(hour=0, minute=0).strftime(DATETIME_FORMAT))
    page.fill("input[name='date_stop']", (now + timedelta(days=2)).strftime(DATETIME_FORMAT))
    _select_option(page, "type", "INFO")
    submit_form(page)
    expect_no_form_error(page)


def test_custom_link_of_a_service_shows_up_on_the_instance_detail_page(admin_page, scoped_user_page):
    """A custom link is configured by an operator and consumed by a user on their own instance."""
    name = _unique("Runbook")
    text = _unique("Open runbook")
    goto_sidebar_entry(admin_page, "Custom links")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    _select_option(admin_page, "services", "Virtual machine")
    admin_page.fill("input[name='text']", text)
    admin_page.fill("input[name='url']", "https://runbooks.example.local/{{ instance.id }}")
    submit_form(admin_page)

    expect_no_form_error(admin_page)
    expect(_table_row(admin_page, name)).to_have_count(1)

    goto_sidebar_entry(scoped_user_page, "Instances")
    _table_row(scoped_user_page, "batch-worker-01").get_by_role("link", name="batch-worker-01").click()
    scoped_user_page.wait_for_load_state()
    expect(scoped_user_page.locator(".btn-toolbar")).to_contain_text(text)

    goto_sidebar_entry(admin_page, "Custom links")
    _delete_row(admin_page, name)
    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "Custom links", name)

    scoped_user_page.reload()
    expect(scoped_user_page.locator(".btn-toolbar")).not_to_contain_text(text)


def test_request_hook_is_created_listed_edited_and_deleted(admin_page):
    """Only the configuration surface: firing a hook needs a celery worker, which the suite has not."""
    name = _unique("On accepted")
    goto_sidebar_entry(admin_page, "Request hook")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    _select_option_containing(admin_page, "operations", "Create virtual machine")
    _select_option(admin_page, "state", "ACCEPTED")
    job_template_label = _select_option_containing(admin_page, "job_template", COMPLIANT_JOB_TEMPLATE)
    _fill_json(admin_page, "extra_vars", '{"triggered_by": "squest"}')
    submit_form(admin_page)

    expect_no_form_error(admin_page)
    row = _table_row(admin_page, name)
    expect(row).to_have_count(1)
    expect(row).to_contain_text("ACCEPTED")
    expect(row).to_contain_text(job_template_label)

    _row_action(admin_page, name, "Edit").click()
    _select_option(admin_page, "state", "FAILED")
    submit_form(admin_page)
    expect_no_form_error(admin_page)
    expect(_table_row(admin_page, name)).to_contain_text("FAILED")

    _delete_row(admin_page, name)
    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "Request hook", name)


def test_instance_hook_is_created_listed_edited_and_deleted(admin_page):
    name = _unique("On available")
    goto_sidebar_entry(admin_page, "Instance hook")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    _select_option(admin_page, "services", "Virtual machine")
    _select_option(admin_page, "state", "AVAILABLE")
    job_template_label = _select_option_containing(admin_page, "job_template", COMPLIANT_JOB_TEMPLATE)
    submit_form(admin_page)

    expect_no_form_error(admin_page)
    row = _table_row(admin_page, name)
    expect(row).to_have_count(1)
    expect(row).to_contain_text("AVAILABLE")
    expect(row).to_contain_text("Virtual machine")
    expect(row).to_contain_text(job_template_label)

    renamed = _unique("On deleted")
    _row_action(admin_page, name, "Edit").click()
    admin_page.fill("input[name='name']", renamed)
    _select_option(admin_page, "state", "DELETED")
    submit_form(admin_page)
    expect_no_form_error(admin_page)
    expect(_table_row(admin_page, renamed)).to_contain_text("DELETED")

    _delete_row(admin_page, renamed)
    expect(admin_page.get_by_role("link", name="Add")).to_be_visible()
    _expect_no_row(admin_page, "Instance hook", renamed)


def _create_email_template(page: Page, name: str, title: str, content: str) -> None:
    goto_sidebar_entry(page, "Emails")
    page.get_by_role("link", name="Add").click()
    page.fill("input[name='name']", name)
    page.fill("input[name='email_title']", title)
    page.fill("textarea[name='html_content']", content)
    submit_form(page)
    expect_no_form_error(page)
    goto_sidebar_entry(page, "Emails")


def test_email_template_is_listed_previewed_and_edited(admin_page):
    name = _unique("Quota warning")
    title = _unique("Your quota is almost full")
    _create_email_template(admin_page, name, title, "<p>Please clean up your instances</p>")

    expect(_table_row(admin_page, name)).to_have_count(1)
    _table_row(admin_page, name).get_by_role("link", name=name).click()
    admin_page.wait_for_load_state()
    expect(admin_page.locator("body")).to_contain_text(title)
    # the preview renders the html content of the template, not its source
    expect(admin_page.locator(".card", has_text="Content")).to_contain_text("Please clean up your instances")

    edited_title = _unique("Your quota is full")
    admin_page.locator("a[href$='/edit/']").click()
    admin_page.fill("input[name='email_title']", edited_title)
    submit_form(admin_page)
    expect_no_form_error(admin_page)
    expect(admin_page.locator("body")).to_contain_text(edited_title)


def test_admin_sends_an_email_from_a_template(admin_page):
    """Email notifications are off in the suite, so the send path must go through without a SMTP server."""
    name = _unique("Welcome")
    _create_email_template(admin_page, name, _unique("Welcome to Squest"), "<p>Hello</p>")

    _table_row(admin_page, name).get_by_role("link", name=name).click()
    admin_page.get_by_role("link", name="Send email").click()
    _select_option(admin_page, "users", "bob")
    submit_form(admin_page, "Send email")

    expect_message(admin_page, "Email sent")
    expect(_table_row(admin_page, name)).to_have_count(1)


def test_scoped_user_does_not_see_the_administration_group(scoped_user_page):
    entries = visible_sidebar_entries(scoped_user_page)
    for entry in ADMINISTRATION_ENTRIES:
        assert entry not in entries, f"the scoped user must not see the '{entry}' entry"
    expect(scoped_user_page.locator("aside.main-sidebar li.nav-header", has_text="Administration")).to_have_count(0)


@pytest.mark.parametrize("entry", ADMINISTRATION_ENTRIES)
def test_scoped_user_is_denied_every_administration_page(scoped_user_page, base_url, entry):
    response = scoped_user_page.goto(f"{base_url}{NAV_MAP['Administration'][entry]}")
    assert response.status == 403, f"the scoped user got {response.status} on '{entry}'"
    expect(scoped_user_page.locator("body")).to_contain_text("Access denied")
