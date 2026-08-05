"""Authentication and the nav map: the flow every other flow starts from.

This spec is also the harness proof: it covers signing in as an admin and as a scoped non admin,
the permission driven sidebar, that every nav map entry answers, and that the stubbed RHAAP/AWX
boundary behaves like a controller (adding a server syncs its job templates in process).
"""
import re
import uuid

import pytest
from playwright.sync_api import expect

from e2e.aap_stub.fake_tower import AUTH_FAILURE_TOKEN
from e2e.helpers import NAV_MAP, expect_form_error, expect_table_contains, expect_table_does_not_contain, \
    goto_sidebar_entry, logout, sidebar_href, submit_form, table_row, visible_sidebar_entries

ADMIN_ONLY_ENTRIES = ["RHAAP/AWX", "Approval workflows", "Role", "Permission", "Users"]
NAV_MAP_ENTRIES = [(group, name, path) for group, entries in NAV_MAP.items() for name, path in entries.items()]


def test_admin_signs_in_and_lands_on_the_home_page(admin_page):
    expect(admin_page).to_have_url(re.compile(r"/ui/$"))
    expect(admin_page.locator("aside.main-sidebar")).to_contain_text("Service catalog")


def test_admin_sees_every_nav_map_group_and_entry(admin_page):
    sidebar = admin_page.locator("aside.main-sidebar")
    for group in NAV_MAP:
        expect(sidebar.locator("li.nav-header", has_text=group)).to_have_count(1)
    entries = visible_sidebar_entries(admin_page)
    for group, name, _ in NAV_MAP_ENTRIES:
        assert name in entries, f"'{name}' of the '{group}' group is missing from the admin sidebar"


def test_scoped_user_sees_a_reduced_sidebar(scoped_user_page):
    """bob holds the 'Squest user' role: consumer entries only, no administration."""
    entries = visible_sidebar_entries(scoped_user_page)
    assert "Service catalog" in entries
    assert "Instances" in entries
    for admin_only in ADMIN_ONLY_ENTRIES:
        assert admin_only not in entries, f"the scoped user must not see the '{admin_only}' entry"
    expect(scoped_user_page.locator("aside.main-sidebar li.nav-header", has_text="Administration")).to_have_count(0)


def test_nav_map_still_matches_the_sidebar(admin_page):
    """NAV_MAP is what the specs navigate with: it must keep matching what the sidebar renders."""
    for group, name, path in NAV_MAP_ENTRIES:
        assert sidebar_href(admin_page, name) == path, f"the sidebar sends '{name}' somewhere else"


@pytest.mark.parametrize("group,name,path", NAV_MAP_ENTRIES, ids=[name for _, name, _ in NAV_MAP_ENTRIES])
def test_every_nav_map_entry_answers_for_an_admin(admin_page, base_url, group, name, path):
    response = admin_page.goto(f"{base_url}{path}")
    assert response.status == 200, f"'{name}' ({path}) answered {response.status}"
    expect(admin_page.locator("aside.main-sidebar")).to_be_visible()


def test_admin_reaches_the_instance_list_through_the_sidebar(admin_page):
    goto_sidebar_entry(admin_page, "Instances")
    expect(admin_page).to_have_url(re.compile(r"/instance/"))
    expect(table_row(admin_page, "web-frontend-01")).to_have_count(1)


def test_admin_reaches_a_treeview_entry_through_the_sidebar(admin_page):
    """'Role' lives under the collapsed RBAC treeview: reaching it means the treeview was opened.

    AdminLTE renders treeview children into the DOM and hides them with CSS, so a helper that only
    checks whether the link exists clicks something invisible and times out.
    """
    goto_sidebar_entry(admin_page, "Role")
    expect(admin_page).to_have_url(re.compile(r"/profiles/role/"))
    expect(table_row(admin_page, "Squest user")).to_have_count(1)


def test_scoped_user_only_sees_the_instances_of_their_own_scope(scoped_user_page, base_url):
    scoped_user_page.goto(f"{base_url}{NAV_MAP['Service catalog']['Instances']}")
    expect_table_contains(scoped_user_page, "batch-worker-01")
    expect_table_does_not_contain(scoped_user_page, "campaign-site")


def test_anonymous_visitor_is_sent_to_the_login_form(page, base_url):
    page.goto(f"{base_url}/ui/service-catalog/instance/")
    expect(page).to_have_url(re.compile(r"/accounts/login/"))
    expect(page.locator("input[name='username']")).to_be_visible()


def test_wrong_password_is_rejected(page, base_url):
    page.goto(f"{base_url}/accounts/login/")
    page.fill("input[name='username']", "bob")
    page.fill("input[name='password']", "not-the-password")
    page.click("button[type='submit']")
    expect(page.locator("p.text-danger")).to_contain_text("didn't match")


def test_signing_out_returns_to_the_login_form(admin_page, base_url):
    logout(admin_page)
    expect(admin_page.locator("input[name='username']")).to_be_visible()
    admin_page.goto(f"{base_url}/ui/")
    expect(admin_page).to_have_url(re.compile(r"/accounts/login/"))


def test_two_users_can_be_driven_side_by_side(admin_page, login_as):
    """The harness must let a spec act as an approver and as a requester in the same test.

    Both pages are reloaded after the second sign in: that is what proves the two sessions are
    independent instead of sharing one cookie jar, where the last sign in would win.
    """
    carol_page = login_as("carol")
    admin_page.reload()
    carol_page.reload()
    expect(carol_page.locator("nav.main-header")).to_contain_text("carol")
    expect(admin_page.locator("nav.main-header")).to_contain_text("admin")
    expect(admin_page.locator("aside.main-sidebar li.nav-header", has_text="Administration")).to_have_count(1)
    expect(carol_page.locator("aside.main-sidebar li.nav-header", has_text="Administration")).to_have_count(0)


def test_adding_an_aap_server_syncs_its_job_templates(admin_page, base_url):
    """Proves the stubbed AAP boundary: the form validates a token and the sync imports templates."""
    # the host is unique in the database, and E2E_REUSE_DB re-runs a spec against a kept database
    name = f"Stubbed AAP {uuid.uuid4().hex[:8]}"
    admin_page.goto(f"{base_url}{NAV_MAP['Administration']['RHAAP/AWX']}")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", name)
    admin_page.fill("input[name='host']", f"https://{uuid.uuid4().hex[:8]}.aap.stub.local")
    admin_page.fill("input[name='token']", "a-token-the-stub-accepts")
    submit_form(admin_page)

    expect(table_row(admin_page, name)).to_have_count(1)
    table_row(admin_page, name).get_by_role("link").first.click()
    admin_page.get_by_role("link", name="Job templates").click()
    job_templates = admin_page.locator("#jobtemplates")
    expect(job_templates).to_contain_text("Deploy virtual machine")
    expect(job_templates).to_contain_text("Decommission virtual machine")


def test_an_aap_server_whose_token_is_refused_is_not_created(admin_page, base_url):
    """The other side of the stubbed boundary: a controller refusing a token surfaces as a form error."""
    admin_page.goto(f"{base_url}{NAV_MAP['Administration']['RHAAP/AWX']}")
    admin_page.get_by_role("link", name="Add").click()
    admin_page.fill("input[name='name']", f"Refused AAP {uuid.uuid4().hex[:8]}")
    admin_page.fill("input[name='host']", f"https://{uuid.uuid4().hex[:8]}.aap.stub.local")
    admin_page.fill("input[name='token']", AUTH_FAILURE_TOKEN)
    submit_form(admin_page)

    expect_form_error(admin_page, "Fail to authenticate with provided token")


def test_scoped_user_cannot_reach_the_administration_pages(scoped_user_page, base_url):
    response = scoped_user_page.goto(f"{base_url}{NAV_MAP['Administration']['RHAAP/AWX']}")
    assert response.status == 403, f"the scoped user got {response.status} on the AAP server list"
    # the page names the permission it wanted, which a page failing for another reason would not
    expect(scoped_user_page.locator("body")).to_contain_text("service_catalog.list_towerserver")
