from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import WorldMixin, make_task, make_team, make_user
from projects.models import Project
from tasks.models import Task, TimeLog

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

class TeamPagesTests(WorldMixin, TestCase):
    def list_context(self, user, **params):
        self.client.force_login(user)
        return self.client.get(reverse('teams:list'), params).context

    def test_list_cards_and_team_numbers(self):
        make_task(self.project, assigned_user=self.leader, status=Task.Status.DONE)
        context = self.list_context(self.member)
        team = context['teams'][0]
        self.assertEqual((team.member_count, team.project_count, team.open_tasks), (3, 1, 1))
        self.assertEqual(len(team.preview), 3)
        self.assertEqual([card['value'] for card in context['cards']], [1, 3, 1, 1])

    def test_avatar_preview_is_limited_to_five(self):
        make_team(leader=self.leader, members=[make_user() for _ in range(6)], name='Grande')
        teams = {team.name: team for team in self.list_context(self.leader)['teams']}
        self.assertEqual(len(teams['Grande'].preview), 5)
        self.assertEqual(teams['Grande'].extra_members, 2)

    def test_search_filters_by_name(self):
        make_team(leader=self.outsider, name='Alfa Beta')
        context = self.list_context(self.admin, q='alfa')
        self.assertEqual([team.name for team in context['teams']], ['Alfa Beta'])
        self.assertEqual(context['q'], 'alfa')
        self.assertEqual(self.list_context(self.admin, q='zzz')['teams'], [])

    def test_detail_cards_members_and_projects(self):
        today = timezone.localdate()
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        make_task(self.project, assigned_user=self.member, due_date=today - timedelta(days=1))
        TimeLog.objects.create(task=self.task, user=self.member, date=today, hours=Decimal('3'))
        self.client.force_login(self.member)
        context = self.client.get(reverse('teams:detail', args=[self.team.pk])).context

        cards = context['cards']
        self.assertEqual([card['value'] for card in cards], [3, 1, 2, '3'])
        self.assertEqual(cards[2]['caption'], '1 vencida')
        rows = {row.user.username: row for row in context['memberships']}
        self.assertEqual((rows['member'].total, rows['member'].done, rows['member'].percent), (3, 1, 33))
        self.assertEqual(rows['leader'].total, 0)
        self.assertEqual([project.pk for project in context['projects']], [self.project.pk])

    def test_member_form_is_only_for_those_who_manage_the_team(self):
        url = reverse('teams:detail', args=[self.team.pk])
        self.client.force_login(self.member)
        self.assertIsNone(self.client.get(url).context['member_form'])
        self.client.force_login(self.leader)
        self.assertIsNotNone(self.client.get(url).context['member_form'])