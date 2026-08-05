"""Helpers shared by the Playwright specs.

Everything here is about Squest's shell (AdminLTE sidebar, django-tables2 lists, the generic
form/confirm templates), so a spec only has to describe the flow it covers.
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

SUBMIT_NAVIGATION_TIMEOUT_MS = 15_000
TREEVIEW_OPEN_TIMEOUT_MS = 5_000
# the entries of a treeview (RBAC, Extras) hang under one of these
TREEVIEW_PARENT = "li.has-treeview"

# The critical flow surface, derived from ``generate_sidebar`` in
# ``profiles/templatetags/squest_utils.py``: sidebar group -> entry -> URL path. Sub entries of a
# treeview are listed under their own name.
NAV_MAP = {
    "Service catalog": {
        "Service catalog": "/ui/service-catalog/",
        "Requests": "/ui/service-catalog/request/",
        "Instances": "/ui/service-catalog/instance/",
        "Support": "/ui/service-catalog/support/",
        "Docs": "/ui/service-catalog/doc/",
    },
    "Resource tracking": {
        "Attributes": "/ui/resource-tracker/attribute/",
        "Resource groups": "/ui/resource-tracker/resource-group/",
        "Graph": "/ui/resource-tracker/graph/",
        "Quota": "/ui/profiles/quota/",
    },
    "Access": {
        "Global scope": "/ui/profiles/global-scope/",
        "Organization": "/ui/profiles/organization/",
        "Team": "/ui/profiles/team/",
        "Users": "/ui/profiles/user/",
    },
    "Administration": {
        "RHAAP/AWX": "/ui/service-catalog/tower/",
        "Approval workflows": "/ui/service-catalog/administration/approval/",
        "Role": "/ui/profiles/role/",
        "Permission": "/ui/profiles/permission/",
        "Default permissions": "/ui/profiles/default-permission/",
        "Request hook": "/ui/service-catalog/tool/global-hook-request/",
        "Instance hook": "/ui/service-catalog/tool/global-hook-instance/",
        "Announcements": "/ui/service-catalog/administration/announcement/",
        "Custom links": "/ui/service-catalog/administration/custom-link/",
        "Emails": "/ui/service-catalog/administration/email-template/",
    },
}


def login(page: Page, base_url: str, username: str, password: str) -> Page:
    """Signs in through the login form and lands on the home page."""
    page.goto(f"{base_url}/accounts/login/")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    expect(page.locator("nav.main-header")).to_contain_text(username)
    return page


def logout(page: Page) -> None:
    page.click("#navbarDropdown2")
    page.click("a.dropdown-item:has-text('Logout')")


def sidebar_entry(page: Page, name: str):
    """The sidebar link of a nav map entry, with the treeview holding it opened.

    AdminLTE renders the children of a treeview into the DOM and hides them with CSS, so a nested
    entry only becomes clickable once its parent is expanded. ``get_by_role`` does not match a
    hidden link, which is what makes a collapsed entry look like a missing one here: the treeview
    parents are clicked until the entry is visible, and an entry the user is not allowed to see
    stays at count zero.
    """
    sidebar = page.locator("aside.main-sidebar")
    entry = sidebar.get_by_role("link", name=name, exact=True)
    if entry.count() == 1:
        return entry
    parents = sidebar.locator(TREEVIEW_PARENT)
    for index in range(parents.count()):
        parent = parents.nth(index)
        # an open treeview would be collapsed by a click, and it is not hiding the entry anyway
        if "menu-open" in (parent.get_attribute("class") or ""):
            continue
        parent.locator("> a.nav-link").click()
        try:
            entry.first.wait_for(state="visible", timeout=TREEVIEW_OPEN_TIMEOUT_MS)
            break
        except PlaywrightTimeoutError:
            pass
    return entry


def reachable_sidebar_entry(page: Page, name: str):
    """``sidebar_entry``, for a caller that needs the entry to be there.

    Without this, an entry the signed in user cannot see (or one the sidebar renamed) reaches
    Playwright as an empty locator and fails on a generic timeout that names a CSS selector rather
    than the entry, which is a long way from 'bob is not allowed to see Role'.
    """
    entry = sidebar_entry(page, name)
    if entry.count() == 0:
        raise AssertionError(f"the sidebar has no '{name}' entry for this user. Visible entries: "
                            f"{visible_sidebar_entries(page)}")
    return entry


def sidebar_href(page: Page, name: str) -> str:
    """The path the sidebar itself points a nav map entry at, used to catch NAV_MAP drift."""
    return reachable_sidebar_entry(page, name).first.get_attribute("href")


def goto_sidebar_entry(page: Page, name: str) -> None:
    """Navigates the way a user does: through the sidebar, not through a URL."""
    with page.expect_navigation():
        reachable_sidebar_entry(page, name).first.click()


def visible_sidebar_entries(page: Page) -> list[str]:
    """Every sidebar entry the signed in user is allowed to see, treeview children included.

    "Visible" is about permissions, not about CSS: ``innerText`` falls back to ``textContent`` for a
    collapsed treeview child, so an entry the sidebar renders is listed whether its parent happens
    to be open or not. That is what the negative assertions want (an entry a user may not see is not
    rendered at all), and the opposite of ``sidebar_entry``, whose ``get_by_role`` ignores a hidden
    link.
    """
    return [text.strip() for text in page.locator("aside.main-sidebar .nav-link p").all_inner_texts() if text.strip()]


def django_messages(page: Page) -> list[str]:
    return [text.strip() for text in page.locator("#django_message_container .alert").all_inner_texts()]


def expect_message(page: Page, text: str) -> None:
    expect(page.locator("#django_message_container")).to_contain_text(text)


# ``generics/form_edit.html`` renders the form errors in an alert that is a sibling of the form, not a
# descendant of it, so the locator has to reach out of the form — but only as far as the card body
# holding it, or an unrelated danger alert on the page (a compliancy warning) would read as a form error
FORM_ERRORS = ".card-body:has(form) > .alert-danger"


def expect_no_form_error(page: Page) -> None:
    expect(page.locator(FORM_ERRORS)).to_have_count(0)


def expect_form_error(page: Page, text: str) -> None:
    """The form came back with ``text`` in its error alert, e.g. a rejected field value."""
    expect(page.locator(FORM_ERRORS)).to_contain_text(text)


def table_rows(page: Page):
    return page.locator("table.table tbody tr")


def table_row(page: Page, text: str):
    """The list row holding ``text``, e.g. the row of an instance in the instance list."""
    return table_rows(page).filter(has_text=text)


def expect_table_contains(page: Page, text: str) -> None:
    expect(table_row(page, text)).to_have_count(1)


def expect_table_does_not_contain(page: Page, text: str) -> None:
    """No row of the list holds ``text``: how a scope boundary shows up to a user.

    Pair it with a positive assertion (``expect_table_contains``) so that a list which failed to
    render at all cannot satisfy it.
    """
    expect(table_row(page, text)).to_have_count(0)


def submit_form(page: Page, label: str = None) -> None:
    """Submits the generic form/confirm template, optionally picking a named button.

    Waits for the navigation the submit triggers, so that an assertion right after it cannot be
    satisfied by the page the form was submitted from. A form that answers without navigating (an
    in page error, an ajax submit) is not an error here: the assertions in the spec decide.
    """
    button = page.locator("form button[type='submit']").first if label is None \
        else page.locator("form").get_by_role("button", name=label).first
    # resolved before the tolerant block below, so a button that cannot be clicked at all is not
    # mistaken for a form that answered without navigating
    button.wait_for(state="visible")
    try:
        with page.expect_navigation(timeout=SUBMIT_NAVIGATION_TIMEOUT_MS):
            button.click()
    except PlaywrightTimeoutError:
        pass


def expect_permission_denied(page: Page) -> None:
    """Squest answers 403 with its own template for a scope the user is not allowed to see."""
    expect(page.locator("body")).to_contain_text("403")
