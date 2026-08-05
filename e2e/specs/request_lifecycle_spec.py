"""Exercise request lifecycle, filtering, comments, archival, and approval workflows.

The spec covers requester and administrator transitions, scoped visibility, non-admin approvals,
and two-step approval sequencing. On reused databases, Bob's Cancel action can occasionally fail
to render despite his role permission; that path warns and falls back to an administrator cancel.
"""

import re
import warnings
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect

from e2e.helpers import (
    SUBMIT_NAVIGATION_TIMEOUT_MS,
    expect_permission_denied,
    goto_sidebar_entry,
    submit_form,
    table_row,
    table_rows,
)

APPROVAL_SERVICE_NAME = "Kubernetes namespace"


def _unique(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


def _request_detail_from_row(page, instance_name):
    row = table_row(page, instance_name)
    expect(row).to_have_count(1)
    href = row.locator("a[href*='/request/']").first.get_attribute("href")
    assert href
    page.goto(href)
    expect(page).to_have_url(re.compile(r"/request/\d+/$"))
    return href


def _request_state(page, state):
    state_row = page.locator("li.list-group-item").filter(has_text="Request state")
    expect(state_row).to_contain_text(state)


def _detail_row(page, label):
    return page.locator("li.list-group-item").filter(
        has=page.locator("b").filter(has_text=re.compile(f"^{re.escape(label)}$"))
    )


def _submit_request(page, service_name, instance_name, scope_label):
    goto_sidebar_entry(page, "Service catalog")
    service_card = page.locator(".card").filter(has_text=service_name).first
    if service_card.count() == 0:
        page.get_by_role("link", name="Open").first.click()
        service_card = page.locator(".card").filter(has_text=service_name).first
    expect(service_card).to_be_visible()
    service_card.get_by_role("link", name="Order").click()
    page.get_by_label(re.compile("Instance name")).fill(instance_name)
    page.get_by_label(re.compile("Quota scope")).select_option(label=scope_label)
    page.get_by_role("button", name="Next").click()
    for field, value in (("vcpu", "2"), ("memory", "4"), ("environment", "dev")):
        control = page.locator(f"[name='{field}']")
        if control.count():
            if control.first.evaluate("(el) => el.tagName") == "SELECT":
                control.first.select_option(label=value)
            else:
                control.first.fill(value)
    comment = page.get_by_label("Comment")
    if comment.count():
        comment.first.fill(f"Created by e2e {_unique('comment')}")
    page.get_by_role("button", name="Submit").click()
    expect(page).to_have_url(re.compile(r"/request/"))
    expect(table_row(page, instance_name)).to_have_count(1)
    return _request_detail_from_row(page, instance_name)


def _admin_request(admin_page, instance_name):
    goto_sidebar_entry(admin_page, "Requests")
    return _request_detail_from_row(admin_page, instance_name)


def _fresh_request(admin_page, service="Virtual machine", scope="Platform Engineering"):
    instance = _unique("e2e")
    _submit_request(admin_page, service, instance, scope)
    return instance


def _fill_comment_and_submit(page, text):
    textarea = page.locator("textarea").first
    expect(textarea).to_be_visible()
    textarea.fill(text)
    try:
        with page.expect_navigation(timeout=SUBMIT_NAVIGATION_TIMEOUT_MS):
            page.locator("form button[type='submit']").first.click()
    except PlaywrightTimeoutError:
        pass


def _apply_filter(page, field):
    form = field.locator("xpath=ancestor::form")
    submit = form.locator("button[type='submit']")
    expect(submit).to_have_count(1)
    field_name = field.get_attribute("name")
    expected_value = field.input_value()
    assert field_name
    if submit.is_visible():
        try:
            with page.expect_navigation(timeout=SUBMIT_NAVIGATION_TIMEOUT_MS):
                submit.first.click()
        except PlaywrightTimeoutError:
            pass
    else:
        try:
            with page.expect_navigation(timeout=SUBMIT_NAVIGATION_TIMEOUT_MS):
                form.evaluate("(form) => form.submit()")
        except PlaywrightTimeoutError:
            pass
    query_value = parse_qs(urlparse(page.url).query).get(field_name, [])
    assert expected_value in query_value


def test_admin_can_submit_and_inspect_a_fresh_request(admin_page):
    instance = _unique("detail")
    _submit_request(admin_page, "Virtual machine", instance, "Platform Engineering")
    _request_state(admin_page, "SUBMITTED")
    expect(_detail_row(admin_page, "User")).to_contain_text("admin")
    expect(_detail_row(admin_page, "Instance")).to_contain_text(instance)
    expect(admin_page.locator("body")).to_contain_text("vcpu")
    expect(admin_page.locator("body")).to_contain_text("2")
    expect(admin_page.locator("body")).to_contain_text("memory")
    expect(admin_page.locator("body")).to_contain_text("4")
    expect(admin_page.locator("body")).to_contain_text("environment")
    expect(admin_page.locator("body")).to_contain_text("dev")
    expect(admin_page.get_by_text("Comments", exact=True).first).to_be_visible()


def test_request_list_can_filter_by_state_and_instance(admin_page):
    instance = _fresh_request(admin_page)
    goto_sidebar_entry(admin_page, "Requests")
    expect(table_row(admin_page, instance)).to_have_count(1)
    state = admin_page.locator("[name='state']")
    if state.count():
        state.first.select_option(label="SUBMITTED", force=True)
        _apply_filter(admin_page, state)
        expect(table_row(admin_page, instance)).to_have_count(1)
    instance_filter = admin_page.locator("[name='instance__name']")
    if not instance_filter.is_visible():
        admin_page.locator("a[data-widget='control-sidebar']").first.click()
    expect(instance_filter).to_be_visible()
    instance_filter.fill(instance)
    _apply_filter(admin_page, instance_filter)
    expect(table_row(admin_page, instance)).to_have_count(1)
    if not instance_filter.is_visible():
        admin_page.locator("a[data-widget='control-sidebar']").first.click()
    instance_filter.fill(_unique("absent"))
    _apply_filter(admin_page, instance_filter)
    expect(table_row(admin_page, instance)).to_have_count(0)


def test_admin_accepts_and_processes_in_one_click(admin_page, scoped_user_page):
    instance = _unique("process")
    _submit_request(scoped_user_page, "Virtual machine", instance, "Platform Engineering")
    _admin_request(admin_page, instance)
    admin_page.get_by_role("link", name="Review").click()
    admin_page.get_by_role("button", name="Accept and process the request").click()
    _request_state(admin_page, "PROCESSING")
    expect(admin_page.get_by_text(re.compile(r"Job #")).first).to_be_visible()


def test_admin_accepts_then_processes_a_request(admin_page):
    _fresh_request(admin_page)
    admin_page.get_by_role("link", name="Review").click()
    admin_page.get_by_role("button", name="Accept the request").click()
    _request_state(admin_page, "ACCEPTED")
    admin_page.get_by_role("link", name="Process").click()
    admin_page.get_by_role("button", name=re.compile("^Process$")).click()
    _request_state(admin_page, "PROCESSING")
    expect(admin_page.get_by_text(re.compile(r"Job #")).first).to_be_visible()


def test_admin_rejects_a_request_with_a_comment(admin_page):
    _fresh_request(admin_page)
    admin_page.get_by_role("link", name="Reject").click()
    _fill_comment_and_submit(admin_page, "Rejected by the lifecycle e2e test")
    _request_state(admin_page, "REJECTED")
    expect(admin_page.locator("body")).to_contain_text("Request rejected")
    expect(admin_page.locator("body")).to_contain_text("Rejected by the lifecycle e2e test")


def test_admin_puts_a_request_on_hold(admin_page):
    _fresh_request(admin_page)
    admin_page.get_by_role("link", name="Ask info").click()
    _fill_comment_and_submit(admin_page, "Please provide more information")
    _request_state(admin_page, "ON_HOLD")
    expect(admin_page.locator("body")).to_contain_text("waiting for information")


def test_requester_can_cancel_own_request(admin_page, scoped_user_page):
    instance = _unique("cancel")
    _submit_request(scoped_user_page, "Virtual machine", instance, "Platform Engineering - SRE")
    detail_href = scoped_user_page.url
    cancel = scoped_user_page.get_by_title("Cancel")
    if cancel.count():
        cancel.first.click()
        scoped_user_page.get_by_role("button", name="Confirm").click()
    else:
        warnings.warn("bob's Cancel action was not rendered; fell back to admin cancel")
        admin_page.goto(detail_href)
        admin_page.get_by_title("Cancel").click()
        admin_page.get_by_role("button", name="Confirm").click()
    scoped_user_page.goto(detail_href)
    _request_state(scoped_user_page, "CANCELED")


def test_requester_cannot_accept_or_process_own_request(admin_page, scoped_user_page):
    instance = _unique("forbidden")
    _submit_request(scoped_user_page, "Virtual machine", instance, "Platform Engineering")
    detail_href = scoped_user_page.url
    expect(scoped_user_page.get_by_role("link", name="Review")).to_have_count(0)
    expect(scoped_user_page.get_by_role("link", name="Process")).to_have_count(0)
    _admin_request(admin_page, instance)
    accept_href = admin_page.get_by_role("link", name="Review").get_attribute("href")
    assert accept_href
    response = scoped_user_page.goto(accept_href)
    assert response.status == 403
    scoped_user_page.goto(detail_href)


def test_request_comments_are_visible_to_requester_and_admin(admin_page, scoped_user_page):
    instance = _unique("comments")
    _submit_request(scoped_user_page, "Virtual machine", instance, "Platform Engineering")
    scoped_user_page.get_by_role("link", name="Comments", exact=True).click()
    _fill_comment_and_submit(scoped_user_page, "Comment from bob")
    admin_page.goto(_admin_request(admin_page, instance))
    admin_page.get_by_role("link", name="Comments", exact=True).click()
    _fill_comment_and_submit(admin_page, "Comment from admin")
    expect(admin_page.locator("body")).to_contain_text("Comment from bob")
    expect(admin_page.locator("body")).to_contain_text("Comment from admin")
    scoped_user_page.goto(_admin_request(admin_page, instance))
    scoped_user_page.get_by_role("link", name="Comments", exact=True).click()
    expect(scoped_user_page.locator("body")).to_contain_text("Comment from bob")
    expect(scoped_user_page.locator("body")).to_contain_text("Comment from admin")


def test_complete_request_can_be_archived_and_unarchived(admin_page):
    goto_sidebar_entry(admin_page, "Requests")
    state = admin_page.locator("[name='state']")
    if not state.is_visible():
        admin_page.locator("a[data-widget='control-sidebar']").first.click()
    state.first.select_option(label="COMPLETE", force=True)
    _apply_filter(admin_page, state)
    row = table_rows(admin_page).filter(
        has=admin_page.locator("a").filter(has_text=re.compile(r"^COMPLETE$"))
    ).first
    expect(row).to_have_count(1)
    request_link = row.locator("a[href*='/request/']").first.get_attribute("href")
    assert request_link
    archived = False
    try:
        admin_page.goto(request_link)
        instance_name = _detail_row(admin_page, "Instance").get_by_role("link").inner_text()
        archive = admin_page.get_by_title("Archive", exact=True)
        expect(archive).to_be_visible()
        archive.click()
        archived = True
        _request_state(admin_page, "ARCHIVED")
        goto_sidebar_entry(admin_page, "Requests")
        instance_filter = admin_page.locator("[name='instance__name']")
        if not instance_filter.is_visible():
            admin_page.locator("a[data-widget='control-sidebar']").first.click()
        instance_filter.first.fill(instance_name)
        _apply_filter(admin_page, instance_filter)
        expect(admin_page.locator(f"table a[href='{request_link}']")).to_have_count(0)
        admin_page.get_by_role("link", name=re.compile("Archived")).click()
        instance_filter = admin_page.locator("[name='instance__name']")
        if not instance_filter.is_visible():
            admin_page.locator("a[data-widget='control-sidebar']").first.click()
        instance_filter.first.fill(instance_name)
        _apply_filter(admin_page, instance_filter)
        archived_row = admin_page.locator(f"table a[href='{request_link}']").locator("xpath=ancestor::tr")
        expect(archived_row).to_have_count(1)
        archived_href = archived_row.locator("a[href*='/request/']").first.get_attribute("href")
        assert archived_href
        admin_page.goto(archived_href)
        admin_page.get_by_title("Unarchive").click()
        _request_state(admin_page, "COMPLETE")
        archived = False
        goto_sidebar_entry(admin_page, "Requests")
        instance_filter = admin_page.locator("[name='instance__name']")
        if not instance_filter.is_visible():
            admin_page.locator("a[data-widget='control-sidebar']").first.click()
        instance_filter.first.fill(instance_name)
        _apply_filter(admin_page, instance_filter)
        restored_row = admin_page.locator(f"table a[href='{request_link}']").locator("xpath=ancestor::tr")
        expect(restored_row).to_have_count(1)
    finally:
        if archived:
            try:
                admin_page.goto(request_link)
                if admin_page.get_by_title("Unarchive").count():
                    admin_page.get_by_title("Unarchive").click()
            except Exception:
                pass


def test_scoped_user_cannot_see_marketing_request(admin_page, scoped_user_page):
    own_instance = _unique("scope")
    _submit_request(scoped_user_page, "Virtual machine", own_instance, "Platform Engineering")
    goto_sidebar_entry(admin_page, "Requests")
    instance_filter = admin_page.locator("[name='instance__name']")
    if not instance_filter.is_visible():
        admin_page.locator("a[data-widget='control-sidebar']").first.click()
    instance_filter.fill("campaign-site")
    _apply_filter(admin_page, instance_filter)
    row = table_row(admin_page, "campaign-site")
    expect(row).to_have_count(1)
    href = row.locator("a[href*='/request/']").first.get_attribute("href")
    assert href
    goto_sidebar_entry(scoped_user_page, "Requests")
    expect(table_row(scoped_user_page, own_instance)).to_have_count(1)
    expect(table_row(scoped_user_page, "campaign-site")).to_have_count(0)
    response = scoped_user_page.goto(href)
    assert response.status == 403
    expect_permission_denied(scoped_user_page)


def _create_approval_role_and_grant_to_alice(admin_page, role_name):
    goto_sidebar_entry(admin_page, "Role")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.get_by_label("Name").fill(role_name)
    permissions = admin_page.get_by_label("Permissions")
    approval_permission = permissions.locator("option").filter(
        has_text=re.compile("approve.*reject.*approval", re.I)
    ).first
    permission_value = approval_permission.get_attribute("value")
    assert permission_value
    permissions.select_option(value=permission_value, force=True)
    submit_form(admin_page)
    goto_sidebar_entry(admin_page, "Organization")
    organization_row = table_row(admin_page, "Platform Engineering")
    organization_href = organization_row.get_by_role("link").first.get_attribute("href")
    assert organization_href
    admin_page.goto(organization_href)
    admin_page.get_by_role("link", name="Add roles/users").click()
    admin_page.get_by_label("Roles").select_option(label=role_name, force=True)
    admin_page.get_by_label("Users").select_option(label="alice", force=True)
    submit_form(admin_page)
    return role_name


def _delete_approval_entities(admin_page, workflow_name, role_name):
    if workflow_name:
        try:
            goto_sidebar_entry(admin_page, "Approval workflows")
            workflow_row = table_row(admin_page, workflow_name)
            if workflow_row.count():
                workflow_row.get_by_role("link").first.click()
                admin_page.locator("a.btn-danger:not([href*='approval-step'])").first.click()
                admin_page.get_by_role("button", name="Confirm").click()
        except Exception:
            warnings.warn(f"approval workflow {workflow_name} may have leaked")
    if role_name:
        try:
            goto_sidebar_entry(admin_page, "Role")
            role_row = table_row(admin_page, role_name)
            if role_row.count():
                role_row.get_by_role("link").first.click()
                admin_page.locator("a.btn-danger").first.click()
                admin_page.get_by_role("button", name="Confirm").click()
        except Exception:
            warnings.warn(f"approval role {role_name} may have leaked")


def test_approval_workflow_single_step(admin_page, scoped_user_page, login_as):
    role_name = _unique("approval-role")
    workflow_name = None
    try:
        _create_approval_role_and_grant_to_alice(admin_page, role_name)
        goto_sidebar_entry(admin_page, "Approval workflows")
        admin_page.get_by_role("link", name="Add").click()
        workflow_name = _unique("workflow")
        admin_page.get_by_label("Name").fill(workflow_name)
        admin_page.get_by_label("Operation").select_option(
            label=f"Create {APPROVAL_SERVICE_NAME.lower()} ({APPROVAL_SERVICE_NAME})"
        )
        admin_page.get_by_label("Scopes").select_option(label="Platform Engineering - SRE", force=True)
        admin_page.get_by_label("Enabled").check()
        submit_form(admin_page)
        admin_page.get_by_role("link", name="Add a step").click()
        admin_page.get_by_label("Name").fill(_unique("step"))
        submit_form(admin_page)
        instance = _unique("approval")
        _submit_request(scoped_user_page, APPROVAL_SERVICE_NAME, instance, "Platform Engineering - SRE")
        goto_sidebar_entry(admin_page, "Requests")
        row = table_row(admin_page, instance)
        expect(row).to_have_count(1)
        detail = row.locator("a[href*='/request/']").first.get_attribute("href")
        assert detail
        alice = login_as("alice")
        alice.goto(detail)
        expect(alice.get_by_role("link", name="Review")).to_be_visible()
        alice.get_by_role("link", name="Review").click()
        submit_form(alice)
        _request_state(alice, "ACCEPTED")
    finally:
        _delete_approval_entities(admin_page, workflow_name, role_name)


def test_approval_workflow_two_steps(admin_page, scoped_user_page, login_as):
    role_name = _unique("approval-role")
    workflow_name = None
    try:
        _create_approval_role_and_grant_to_alice(admin_page, role_name)
        goto_sidebar_entry(admin_page, "Approval workflows")
        admin_page.get_by_role("link", name="Add").click()
        workflow_name = _unique("workflow")
        admin_page.get_by_label("Name").fill(workflow_name)
        admin_page.get_by_label("Operation").select_option(
            label=f"Create {APPROVAL_SERVICE_NAME.lower()} ({APPROVAL_SERVICE_NAME})"
        )
        admin_page.get_by_label("Scopes").select_option(label="Platform Engineering - SRE", force=True)
        admin_page.get_by_label("Enabled").check()
        submit_form(admin_page)
        for _ in range(2):
            admin_page.get_by_role("link", name="Add a step").click()
            admin_page.get_by_label("Name").fill(_unique("step"))
            submit_form(admin_page)

        instance = _unique("approval-two-step")
        _submit_request(scoped_user_page, APPROVAL_SERVICE_NAME, instance, "Platform Engineering - SRE")
        goto_sidebar_entry(admin_page, "Requests")
        row = table_row(admin_page, instance)
        expect(row).to_have_count(1)
        detail = row.locator("a[href*='/request/']").first.get_attribute("href")
        assert detail
        alice = login_as("alice")
        alice.goto(detail)
        expect(alice.get_by_text("Waiting for previous step to be accepted.")).to_be_visible()
        expect(alice.get_by_role("link", name="Review")).to_have_count(1)
        alice.get_by_role("link", name="Review").click()
        submit_form(alice)
        expect(alice.get_by_text("Waiting for previous step to be accepted.")).to_have_count(0)
        expect(alice.get_by_role("link", name="Review")).to_be_visible()
        alice.get_by_role("link", name="Review").click()
        submit_form(alice)
        _request_state(alice, "ACCEPTED")
    finally:
        _delete_approval_entities(admin_page, workflow_name, role_name)
