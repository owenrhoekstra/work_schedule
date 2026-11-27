from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from schedule.models import EmployeeTeam

from .factories import make_employee, make_team, make_team_role


class TeamRoleTests(TestCase):
    def test_ordered_by_display_order_then_name(self):
        team = make_team()
        make_team_role("B", order=10, team=team)
        make_team_role("A", order=20, team=team)
        make_team_role("C", order=10, team=team)
        names = [r.name for r in team.team_roles.all()]
        self.assertEqual(names, ["B", "C", "A"])

    def test_name_unique_within_team(self):
        team = make_team()
        make_team_role("Chef", team=team)
        with self.assertRaises(IntegrityError), transaction.atomic():
            team.team_roles.create(name="Chef")

    def test_same_name_allowed_on_different_teams(self):
        make_team_role("Chef", team=make_team(name="Kitchen"))
        make_team_role("Chef", team=make_team(name="Front"))  # no error

    def test_deleting_role_clears_assignment_but_keeps_membership(self):
        role = make_team_role("Chef")
        emp = make_employee(role=role)
        link = EmployeeTeam.objects.get(employee=emp, team=role.team)
        role.delete()
        link.refresh_from_db()
        self.assertIsNone(link.role)

    def test_employee_has_independent_role_per_team(self):
        kitchen = make_team(name="Kitchen")
        front = make_team(name="Front")
        chef = make_team_role("Head Chef", team=kitchen)
        server = make_team_role("Server", team=front)
        emp = make_employee(role=chef)
        EmployeeTeam.objects.create(
            employee=emp,
            team=front,
            role=server,
            valid_from=timezone.localdate() - timedelta(days=1),
        )
        roles = {
            link.team.name: link.role.name
            for link in EmployeeTeam.objects.filter(employee=emp)
        }
        self.assertEqual(roles, {"Kitchen": "Head Chef", "Front": "Server"})
