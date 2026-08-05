"""Access, scopes and RBAC: who can see and do what.

This is the mechanism every other flow's permission assertion leans on. It covers the "Access"
sidebar group (global scope, organizations, teams, users) and the "RBAC" treeview of the
administration group (roles, permissions, default permissions), and it proves the point of the
family by driving two signed in users at once: a scope is invisible to a user until a role is
granted to them in it, and visible right after.

Quotas are covered by the resource tracking spec: only their presence on a scope page is touched
here.
"""
import re
import uuid

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect

from e2e.helpers import NAV_MAP, expect_table_contains, expect_table_does_not_contain, goto_sidebar_entry, \
    submit_form, table_row, visible_sidebar_entries

SQUEST_USER_ROLE = "Squest user"
SEEDED_ORGANIZATION = "Platform Engineering"
SEEDED_ORGANIZATION_INSTANCE = "web-frontend-01"
FOREIGN_ORGANIZATION = "Marketing"


def _unique(prefix):
    """A name no other test and no earlier run (``E2E_REUSE_DB``) can collide with."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _card_title(page):
    return page.locator("h3.card-title").first


def _header_button(page, icon):
    """An icon only edit/delete/filter button of the page header.

    Font Awesome swaps the ``<i>`` Squest renders for an ``<svg>`` that keeps the ``fa-*`` class, so
    the icon has to be matched on the class alone rather than on the tag.
    """
    return page.locator(f".content-header a.btn:has(.fa-{icon})").first


def _open_tab(page, name):
    """Detail pages hide their tables behind AdminLTE tabs, so a spec has to open one first."""
    page.locator("#tabs").get_by_role("link", name=name, exact=True).click()


def _pick(page, field_name, *labels):
    """Picks values in a select: Squest turns every select into a bootstrap-select dropdown.

    Clicking an already selected value unselects it, which is how a multi select is emptied.
    """
    dropdown = page.locator(f"div.bootstrap-select:has(select[name='{field_name}'])")
    toggle = dropdown.locator("button.dropdown-toggle")
    # the native <option> elements are still in the DOM: only the rendered menu must be clicked
    menu = dropdown.locator("ul.dropdown-menu.inner")
    for label in labels:
        if toggle.get_attribute("aria-expanded") != "true":
            toggle.click()
        dropdown.locator(".bs-searchbox input").fill(label)
        menu.get_by_role("option", name=label, exact=True).first.click()
    page.keyboard.press("Escape")


def _filter_list(page, field_name, value):
    """Narrows a list through its filter sidebar, the way a user does on a paginated list."""
    aside = page.locator("aside.control-sidebar")
    field = aside.locator(f"input[name='{field_name}']")
    for _ in range(3):  # the toggle is a no-op until AdminLTE has bound the control sidebar
        if field.is_visible():
            break
        _header_button(page, "sliders-h").click()
        try:
            # long enough that a slow open is waited out rather than toggled shut again
            field.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError:
            continue
    field.fill(value)
    with page.expect_navigation():
        aside.get_by_role("button", name="Apply").click()


def _open_organization(page, name):
    """Opens an organization from its list, narrowed to it: the list is paginated."""
    goto_sidebar_entry(page, "Organization")
    _filter_list(page, "name", name)
    table_row(page, name).get_by_role("link", name=name, exact=True).click()


def _delete_from_its_page(page, url):
    """Deletes an object through its own page. Used by the factories to clean up after a test.

    A refused delete re-renders the confirm page instead of raising, so the page is asked for again:
    a leftover would pollute the session scoped database of every later spec.
    """
    response = page.goto(url)
    if response.status != 200:
        return
    _header_button(page, "trash").click()
    submit_form(page, "Confirm")
    assert page.goto(url).status == 404, f"{url} was not deleted"


def _delete_all(page, urls):
    """Deletes every object a factory created, reporting the survivors rather than the first one."""
    survivors = []
    for url in urls:
        try:
            _delete_from_its_page(page, url)
        except (AssertionError, PlaywrightTimeoutError) as error:
            survivors.append(f"{url} ({error})")
    assert not survivors, "objects left in the session database: " + ", ".join(survivors)


def _tab_rows(page, tab_id, text):
    """The rows of one tab pane: every pane of a detail page is in the DOM, open or not."""
    return page.locator(f"#{tab_id} table tbody tr").filter(has_text=text)


def _grant_role(page, scope_url, role, username, button="Add roles/users"):
    """Adds ``username`` to ``role`` on the scope of ``scope_url``, through its RBAC button."""
    page.goto(scope_url)
    page.get_by_role("link", name=button).click()
    _pick(page, "roles", role)
    _pick(page, "users", username)
    submit_form(page)


def _revoke_user(page, scope_url, username):
    """Removes every role ``username`` holds on the scope, through the trash of its users tab."""
    page.goto(scope_url)
    # the global scope page renders its users table directly, an org/team page behind a tab that
    # only exists once the scope holds a user
    if page.locator("#tabs").get_by_role("link", name="Users", exact=True).count() == 1:
        _open_tab(page, "Users")
    page.locator("table tbody").first.wait_for(state="attached")
    row = table_row(page, username)
    if row.count() == 0:
        return
    row.locator("a.btn-danger").first.click()
    page.wait_for_load_state()
    submit_form(page, "Confirm")


@pytest.fixture
def organization_factory(admin_page):
    """Creates organizations through the UI and deletes the survivors, so lists stay short."""
    created = []

    def _create(name=None):
        name = name or _unique("e2e-org")
        goto_sidebar_entry(admin_page, "Organization")
        admin_page.get_by_role("link", name="Add").click()
        admin_page.fill("[name='name']", name)
        admin_page.fill("[name='description']", f"Organization of {name}")
        submit_form(admin_page)
        expect(_card_title(admin_page)).to_contain_text(name)
        created.append(admin_page.url)
        return name, admin_page.url

    yield _create
    _delete_all(admin_page, created)


@pytest.fixture
def role_factory(admin_page):
    """Creates roles through the UI and deletes them afterwards."""
    created = []

    def _create(permissions, name=None):
        name = name or _unique("e2e-role")
        goto_sidebar_entry(admin_page, "Role")
        admin_page.get_by_role("link", name="Add").click()
        admin_page.fill("[name='name']", name)
        admin_page.fill("[name='description']", f"Role of {name}")
        _pick(admin_page, "permissions", *permissions)
        submit_form(admin_page)
        expect(_card_title(admin_page)).to_contain_text(name)
        created.append(admin_page.url)
        return name, admin_page.url

    yield _create
    _delete_all(admin_page, created)


def test_admin_creates_an_organization_and_reaches_its_detail_page(admin_page, organization_factory):
    name, url = organization_factory()

    expect(admin_page.locator("body")).to_contain_text(f"Organization of {name}")
    _open_tab(admin_page, "Roles")
    expect(admin_page.locator("#role_table")).to_be_visible()

    goto_sidebar_entry(admin_page, "Organization")
    _filter_list(admin_page, "name", name)
    expect_table_contains(admin_page, name)


def test_admin_edits_an_organization(admin_page, organization_factory):
    name, url = organization_factory()
    renamed = f"{name}-renamed"

    _header_button(admin_page, "pencil-alt").click()
    admin_page.fill("[name='name']", renamed)
    submit_form(admin_page)

    expect(_card_title(admin_page)).to_contain_text(renamed)
    goto_sidebar_entry(admin_page, "Organization")
    _filter_list(admin_page, "name", renamed)
    expect_table_contains(admin_page, renamed)


def test_admin_deletes_an_organization(admin_page, organization_factory):
    name, url = organization_factory()

    admin_page.goto(url)
    _header_button(admin_page, "trash").click()
    expect(admin_page.locator("body")).to_contain_text(name)
    submit_form(admin_page, "Confirm")

    expect(admin_page).to_have_url(re.compile(f"{NAV_MAP['Access']['Organization']}$"))
    _filter_list(admin_page, "name", SEEDED_ORGANIZATION)  # the list still lists the untouched ones
    expect_table_contains(admin_page, SEEDED_ORGANIZATION)
    _filter_list(admin_page, "name", name)
    expect_table_does_not_contain(admin_page, name)


def test_admin_creates_and_deletes_a_team_of_an_organization(admin_page, organization_factory):
    organization, organization_url = organization_factory()
    team = _unique("e2e-team")

    admin_page.get_by_role("link", name="Add team").click()
    admin_page.fill("[name='name']", team)
    submit_form(admin_page)

    # a team lives under its organization: its page points back at it and it shows on its teams tab
    expect(_card_title(admin_page)).to_contain_text(team)
    expect(admin_page.locator("body")).to_contain_text(organization)
    team_url = admin_page.url
    admin_page.goto(organization_url)
    _open_tab(admin_page, "Teams")
    expect_table_contains(admin_page, team)

    admin_page.goto(team_url)
    _header_button(admin_page, "trash").click()
    submit_form(admin_page, "Confirm")

    admin_page.goto(organization_url)
    expect(_card_title(admin_page)).to_contain_text(organization)
    expect_table_does_not_contain(admin_page, team)


def test_admin_grants_and_removes_a_role_on_an_organization(admin_page, organization_factory):
    name, url = organization_factory()

    _grant_role(admin_page, url, SQUEST_USER_ROLE, "carol")

    _open_tab(admin_page, "Users")
    expect(table_row(admin_page, "carol")).to_contain_text(SQUEST_USER_ROLE)

    # the small cross of the role button removes that one role
    table_row(admin_page, "carol").locator("a.btn-secondary[title='Delete']").first.click()
    expect(admin_page.locator("body")).to_contain_text(SQUEST_USER_ROLE)
    submit_form(admin_page, "Confirm")

    expect_table_does_not_contain(admin_page, "carol")


def test_admin_grants_and_removes_a_role_on_a_team(admin_page, organization_factory):
    organization, organization_url = organization_factory()
    team = _unique("e2e-team")
    admin_page.get_by_role("link", name="Add team").click()
    admin_page.fill("[name='name']", team)
    submit_form(admin_page)
    team_url = admin_page.url

    # a user has to belong to the organization before they can be added to one of its teams
    _grant_role(admin_page, organization_url, SQUEST_USER_ROLE, "carol")
    _grant_role(admin_page, team_url, SQUEST_USER_ROLE, "carol")

    _open_tab(admin_page, "Users")
    expect(table_row(admin_page, "carol")).to_contain_text(SQUEST_USER_ROLE)

    _revoke_user(admin_page, team_url, "carol")
    expect_table_does_not_contain(admin_page, "carol")

    _delete_from_its_page(admin_page, team_url)


def test_an_organization_stays_invisible_until_a_role_is_granted_in_it(admin_page, organization_factory, login_as):
    """The point of the family, seen by a signed in user: no role, no scope."""
    name, url = organization_factory()
    carol_page = login_as("carol")

    goto_sidebar_entry(carol_page, "Organization")
    expect_table_contains(carol_page, FOREIGN_ORGANIZATION)
    expect_table_does_not_contain(carol_page, name)
    assert carol_page.goto(url).status == 403, "a user without a role on an organization must not open it"

    _grant_role(admin_page, url, SQUEST_USER_ROLE, "carol")

    _open_organization(carol_page, name)
    expect(_card_title(carol_page)).to_contain_text(name)


def test_a_role_on_an_organization_reveals_its_instances(admin_page, login_as, base_url):
    """carol is a Marketing user: the instances of another organization appear only with a role."""
    organization_url = None
    try:
        _open_organization(admin_page, SEEDED_ORGANIZATION)
        organization_url = admin_page.url

        carol_page = login_as("carol")
        goto_sidebar_entry(carol_page, "Instances")
        expect_table_contains(carol_page, "campaign-site")
        expect_table_does_not_contain(carol_page, SEEDED_ORGANIZATION_INSTANCE)

        _grant_role(admin_page, organization_url, SQUEST_USER_ROLE, "carol")

        carol_page.reload()
        expect_table_contains(carol_page, SEEDED_ORGANIZATION_INSTANCE)
    finally:
        if organization_url is not None:
            _revoke_user(admin_page, organization_url, "carol")

    carol_page.reload()
    expect_table_does_not_contain(carol_page, SEEDED_ORGANIZATION_INSTANCE)


def test_a_global_role_adds_the_sidebar_entry_it_unlocks(admin_page, role_factory, scoped_user_page):
    """The sidebar is permission driven: a role granted on the global scope shows up in it."""
    role, _ = role_factory(["list_role", "view_role"])
    assert "Role" not in visible_sidebar_entries(scoped_user_page)

    global_scope_url = None
    try:
        goto_sidebar_entry(admin_page, "Global scope")
        global_scope_url = admin_page.url
        _grant_role(admin_page, global_scope_url, role, "bob", button="Add Global RBAC")
        expect(table_row(admin_page, "bob")).to_contain_text(role)

        scoped_user_page.reload()
        assert "Role" in visible_sidebar_entries(scoped_user_page), \
            "a global role holding list_role must give the user the 'Role' sidebar entry"
        goto_sidebar_entry(scoped_user_page, "Role")
        expect_table_contains(scoped_user_page, SQUEST_USER_ROLE)
    finally:
        if global_scope_url is not None:
            _revoke_user(admin_page, global_scope_url, "bob")

    scoped_user_page.reload()
    assert "Role" not in visible_sidebar_entries(scoped_user_page)


def test_admin_creates_edits_and_deletes_a_role(admin_page, role_factory):
    role, url = role_factory(["list_organization"])

    _open_tab(admin_page, "Permissions")
    expect_table_contains(admin_page, "list_organization")

    _header_button(admin_page, "pencil-alt").click()
    admin_page.fill("[name='description']", "Edited by the access spec")
    submit_form(admin_page)
    expect(admin_page.locator("body")).to_contain_text("Edited by the access spec")

    _header_button(admin_page, "trash").click()
    submit_form(admin_page, "Confirm")
    expect_table_does_not_contain(admin_page, role)


def test_permission_list_can_be_narrowed_to_one_permission(admin_page):
    goto_sidebar_entry(admin_page, "Permission")
    _filter_list(admin_page, "codename", "list_organization")

    expect_table_contains(admin_page, "list_organization")
    expect_table_does_not_contain(admin_page, "list_towerserver")


def test_admin_changes_the_default_permissions_of_the_global_scope(admin_page):
    added_permission = "rename_instance"
    goto_sidebar_entry(admin_page, "Default permissions")
    _open_tab(admin_page, "Owner permissions")
    expect(_tab_rows(admin_page, "owner-permissions", added_permission)).to_have_count(0)

    try:
        _header_button(admin_page, "pencil-alt").click()
        _pick(admin_page, "owner_permissions", added_permission)
        submit_form(admin_page)

        _open_tab(admin_page, "Owner permissions")
        expect(_tab_rows(admin_page, "owner-permissions", added_permission)).to_have_count(1)
    finally:
        # the global scope is shared with every later spec, and picking a value toggles it: the
        # permission is only clicked back off when it really was added
        goto_sidebar_entry(admin_page, "Default permissions")
        admin_page.locator("#owner-permissions table tbody tr").first.wait_for(state="attached")
        if _tab_rows(admin_page, "owner-permissions", added_permission).count() == 1:
            _header_button(admin_page, "pencil-alt").click()
            _pick(admin_page, "owner_permissions", added_permission)
            submit_form(admin_page)

    _open_tab(admin_page, "Owner permissions")
    expect(_tab_rows(admin_page, "owner-permissions", added_permission)).to_have_count(0)
    expect(_tab_rows(admin_page, "owner-permissions", "view_instance")).to_have_count(1)


def test_admin_browses_the_user_list_and_a_user_detail_page(admin_page):
    goto_sidebar_entry(admin_page, "Users")
    for username in ["admin", "alice", "bob", "carol"]:
        expect_table_contains(admin_page, username)

    table_row(admin_page, "bob").get_by_role("link", name="bob", exact=True).click()
    expect(admin_page.locator("body")).to_contain_text("bob@squest.domain")
    _open_tab(admin_page, "Instances")
    expect(admin_page.locator("#instances tbody tr").filter(has_text="batch-worker-01")).to_have_count(1)


def test_scoped_user_cannot_reach_the_access_administration_pages(scoped_user_page, base_url):
    """bob holds the 'Squest user' role on his own scopes only: no user, role or global scope page."""
    # read the sidebar once, off a normal page: a 403 answer renders no sidebar to look at
    entries = visible_sidebar_entries(scoped_user_page)
    for name, path in [("Users", NAV_MAP["Access"]["Users"]),
                       ("Role", NAV_MAP["Administration"]["Role"]),
                       ("Permission", NAV_MAP["Administration"]["Permission"]),
                       ("Global scope", NAV_MAP["Access"]["Global scope"])]:
        assert name not in entries, f"'{name}' must not be in bob's sidebar"
        assert scoped_user_page.goto(f"{base_url}{path}").status == 403, f"'{name}' did not answer 403 for bob"


def test_scoped_user_cannot_open_an_organization_they_hold_no_role_in(scoped_user_page, admin_page):
    _open_organization(admin_page, FOREIGN_ORGANIZATION)
    foreign_organization_url = admin_page.url

    goto_sidebar_entry(scoped_user_page, "Organization")
    expect_table_contains(scoped_user_page, SEEDED_ORGANIZATION)
    expect_table_does_not_contain(scoped_user_page, FOREIGN_ORGANIZATION)
    assert scoped_user_page.goto(foreign_organization_url).status == 403
