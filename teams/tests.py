from django.test import TestCase
from django.urls import reverse

from core.factories import WorldMixin, make_user
from projects.models import Project

from .models import Team, TeamMember


class VisibilityTests(WorldMixin, TestCase):
    def ids(self, user):
        return set(Team.objects.visible_to(user).values_list('pk', flat=True))

    def test_visibility_by_role_and_membership(self):
        self.assertEqual(self.ids(self.admin), {self.team.pk})
        self.assertEqual(self.ids(self.leader), {self.team.pk})
        self.assertEqual(self.ids(self.member), {self.team.pk})
        self.assertEqual(self.ids(self.outsider), set())


class TeamViewTests(WorldMixin, TestCase):
    def test_non_members_get_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('teams:detail', args=[self.team.pk])).status_code, 404)

    def test_member_who_is_not_leader_cannot_manage(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('teams:update', args=[self.team.pk])).status_code, 403)
        response = self.client.post(reverse('teams:member_add', args=[self.team.pk]), {'user': self.outsider.pk})
        self.assertEqual(response.status_code, 403)

    def test_client_can_see_but_not_manage(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('teams:detail', args=[self.team.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage'])
        response = self.client.post(reverse('teams:member_add', args=[self.team.pk]), {'user': self.outsider.pk})
        self.assertEqual(response.status_code, 403)

    def test_leader_adds_and_removes_members(self):
        newcomer = make_user()
        self.client.force_login(self.leader)
        self.client.post(
            reverse('teams:member_add', args=[self.team.pk]),
            {'user': newcomer.pk, 'role_in_team': 'QA'},
        )
        membership = TeamMember.objects.get(team=self.team, user=newcomer)
        self.assertEqual(membership.role_in_team, 'QA')

        self.client.post(reverse('teams:member_remove', args=[membership.pk]))
        self.assertFalse(TeamMember.objects.filter(pk=membership.pk).exists())

    def test_cannot_add_an_existing_member_twice(self):
        self.client.force_login(self.leader)
        before = TeamMember.objects.filter(team=self.team).count()
        self.client.post(reverse('teams:member_add', args=[self.team.pk]), {'user': self.member.pk})
        self.assertEqual(TeamMember.objects.filter(team=self.team).count(), before)

    def test_leader_cannot_be_removed(self):
        membership = TeamMember.objects.get(team=self.team, user=self.leader)
        self.client.force_login(self.leader)
        self.client.post(reverse('teams:member_remove', args=[membership.pk]))
        self.assertTrue(TeamMember.objects.filter(pk=membership.pk).exists())

    def test_creator_becomes_leader_and_member(self):
        self.client.force_login(self.member)
        self.client.post(reverse('teams:create'), {'name': 'Nuevo equipo'})
        team = Team.objects.get(name='Nuevo equipo')
        self.assertEqual(team.leader, self.member)
        self.assertTrue(TeamMember.objects.filter(team=team, user=self.member).exists())

    def test_client_cannot_create_teams(self):
        self.client.force_login(self.client_user)
        response = self.client.post(reverse('teams:create'), {'name': 'Nuevo equipo'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Team.objects.filter(name='Nuevo equipo').exists())

    def test_delete_requires_leader_and_keeps_projects(self):
        url = reverse('teams:delete', args=[self.team.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.leader)
        self.assertRedirects(self.client.post(url), reverse('teams:list'))
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())
        self.assertIsNone(Project.objects.get(pk=self.project.pk).team)