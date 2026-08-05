from django.contrib.auth.models import User
from django.urls import reverse

from profiles.models import Organization, Role, Team
from profiles.tables.organization_table import OrganizationTable
from tests.test_profiles.base.base_test_profile import BaseTestProfile


class OrganizationTableTest(BaseTestProfile):

    def setUp(self):
        super(OrganizationTableTest, self).setUp()
        self.table_org = Organization.objects.create(name="org_for_table")
        self.details_url = reverse("profiles:organization_details", kwargs={'pk': self.table_org.id})
        self.table = OrganizationTable(Organization.objects.filter(id=self.table_org.id))

    def test_render_users_without_user(self):
        self.assertEqual(
            f'<a href="{self.details_url}#users" class="btn btn-secondary bg-sm">0</a>',
            self.table.render_users(value=None, record=self.table_org)
        )

    def test_render_users_counts_users(self):
        role = Role.objects.create(name="role_for_organization_table")
        user = User.objects.create_user('user_for_organization_table', 'user@hpe.com', self.common_password)
        self.table_org.add_user_in_role(user, role)
        self.assertEqual(
            f'<a href="{self.details_url}#users" class="btn btn-secondary bg-sm">1</a>',
            self.table.render_users(value=None, record=self.table_org)
        )

    def test_render_teams_without_team(self):
        self.assertEqual(
            f'<a href="{self.details_url}#teams" class="btn btn-secondary bg-sm">0</a>',
            self.table.render_teams(value=None, record=self.table_org)
        )

    def test_render_teams_counts_teams(self):
        Team.objects.create(org=self.table_org, name="team_for_organization_table")
        self.assertEqual(
            f'<a href="{self.details_url}#teams" class="btn btn-secondary bg-sm">1</a>',
            self.table.render_teams(value=None, record=self.table_org)
        )
