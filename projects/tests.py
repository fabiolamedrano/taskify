from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.factories import WorldMixin, make_project, make_task, make_user
from tasks.models import Comment, Task, TimeLog

from .models import Project


class VisibilityTests(WorldMixin, TestCase):
    def ids(self, user):
        return set(Project.objects.visible_to(user).values_list('pk', flat=True))

    def test_admin_sees_everything(self):
        self.assertEqual(self.ids(self.admin), {self.project.pk, self.hidden_project.pk})

    def test_owner_sees_only_own_project(self):
        self.assertEqual(self.ids(self.leader), {self.project.pk})

    def test_team_member_sees_team_project(self):
        self.assertEqual(self.ids(self.member), {self.project.pk})

    def test_client_in_team_sees_team_project(self):
        self.assertIn(self.project.pk, self.ids(self.client_user))

    def test_assigned_user_sees_project(self):
        other = make_user()
        make_task(self.hidden_project, assigned_user=other)
        self.assertEqual(self.ids(other), {self.hidden_project.pk})

    def test_unrelated_user_sees_nothing(self):
        self.assertEqual(self.ids(make_user()), set())

    def test_task_counts_are_not_inflated_by_joins(self):
        # El proyecto tiene 3 miembros en el equipo; los conteos deben seguir siendo exactos
        make_task(self.project, status=Task.Status.DONE)
        make_task(self.project)
        project = Project.objects.visible_to(self.member).with_task_counts().get(pk=self.project.pk)
        self.assertEqual(project.task_count, 3)
        self.assertEqual(project.done_count, 1)
        self.assertEqual(project.progress, 33)


class ConstraintTests(WorldMixin, TestCase):
    def assertRejected(self, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Project.objects.create(name='Mal', owner=self.leader, **fields)

    def test_negative_budget_is_rejected(self):
        self.assertRejected(budget=Decimal('-1'))

    def test_due_date_cannot_precede_start_date(self):
        self.assertRejected(start_date=date(2026, 10, 10), due_date=date(2026, 10, 1))


class ProjectViewTests(WorldMixin, TestCase):
    def test_login_is_required(self):
        response = self.client.get(reverse('projects:list'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('projects:list')}")

    def test_list_only_shows_visible_projects(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:list'))
        self.assertContains(response, 'Proyecto Visible')
        self.assertNotContains(response, 'Proyecto Oculto')

    def test_hidden_project_returns_404(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:detail', args=[self.hidden_project.pk]))
        self.assertEqual(response.status_code, 404)

    def test_invalid_status_filter_is_ignored(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:list'), {'status': 'inventado'})
        self.assertContains(response, 'Proyecto Visible')

    def test_client_cannot_create_projects(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse('projects:create')).status_code, 403)
        response = self.client.post(reverse('projects:create'), {'name': 'Nuevo', 'status': 'active'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(name='Nuevo').exists())

    def test_member_creates_project_as_owner(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('projects:create'), {'name': 'Mi proyecto', 'status': 'active'},
        )
        project = Project.objects.get(name='Mi proyecto')
        self.assertRedirects(response, project.get_absolute_url())
        self.assertEqual(project.owner, self.member)

    def test_invalid_data_does_not_create_project(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('projects:create'), {
            'name': 'Mal', 'status': 'active', 'budget': '-5',
            'start_date': '2026-10-10', 'due_date': '2026-10-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(name='Mal').exists())
        errors = response.context['form'].errors
        self.assertIn('budget', errors)
        self.assertIn('due_date', errors)

    def test_only_owner_or_admin_can_edit(self):
        url = reverse('projects:update', args=[self.project.pk])
        self.client.force_login(self.member)  # ve el proyecto, pero no es el dueño
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.leader)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_cannot_edit_hidden_project(self):
        self.client.force_login(self.member)
        url = reverse('projects:update', args=[self.hidden_project.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_delete_requires_owner_and_removes_tasks(self):
        url = reverse('projects:delete', args=[self.project.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

        self.client.force_login(self.leader)
        self.assertRedirects(self.client.post(url), reverse('projects:list'))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())

class ProjectListFilterTests(WorldMixin, TestCase):
    def test_status_chips_show_counts_and_keep_the_search(self):
        make_project(self.leader, self.team, name='Pausado web', status=Project.Status.PAUSED)
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:list'), {'q': 'web'})
        options = {option['label']: option for option in response.context['status_options']}
        self.assertEqual(options['Todos']['count'], 1)
        self.assertEqual(options['Pausado']['count'], 1)
        self.assertEqual(options['Activo']['count'], 0)
        self.assertIn('q=web', options['Pausado']['url'])

    def test_clearing_the_search_keeps_the_status(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:list'), {'q': 'web', 'status': 'paused'})
        self.assertEqual(response.context['clear_search_url'], '?status=paused')
        self.assertEqual(response.context['current_status'], 'paused')

class ProjectDetailPageTests(WorldMixin, TestCase):
    def get(self, user, project=None, **params):
        self.client.force_login(user)
        url = reverse('projects:detail', args=[(project or self.project).pk])
        return self.client.get(url, params)

    def test_cards_donut_and_counts(self):
        make_task(self.project, assigned_user=self.leader, status=Task.Status.DONE)
        make_task(self.project)
        context = self.get(self.member).context
        self.assertEqual(context['status_counts'], {'todo': 2, 'doing': 0, 'done': 1})
        self.assertEqual(context['donut']['done_pct'], 33)
        self.assertEqual(context['cards'][1]['value'], 2)
        self.assertEqual(context['cards'][0]['value'], 33)

    def test_my_tasks_and_workload(self):
        make_task(self.project, assigned_user=self.leader, status=Task.Status.DONE)
        make_task(self.project)
        context = self.get(self.member).context
        self.assertEqual([task.pk for task in context['my_tasks']], [self.task.pk])
        rows = {row['name']: row for row in context['workload']}
        self.assertEqual((rows['member']['total'], rows['member']['percent']), (1, 0))
        self.assertEqual(rows['leader']['percent'], 100)
        self.assertEqual(rows['Sin responsable']['total'], 1)

    def test_weekly_hours_bars(self):
        TimeLog.objects.create(
            task=self.task, user=self.member, date=timezone.localdate(), hours=Decimal('4'),
        )
        context = self.get(self.member).context
        bars = context['weekly']
        self.assertEqual(len(bars), 6)
        self.assertTrue(bars[-1]['is_current'])
        self.assertEqual(bars[-1]['total'], Decimal('4'))
        self.assertEqual(bars[0]['percent'], 0)
        self.assertEqual(context['cards'][2]['value'], '4')

    def test_task_filter_and_counts(self):
        make_task(self.project, status=Task.Status.DONE, title='Lista')
        context = self.get(self.member, status='done').context
        self.assertEqual([task.title for task in context['tasks']], ['Lista'])
        options = {option['label']: option for option in context['task_filter']}
        self.assertEqual((options['Todas']['count'], options['Hecho']['count']), (2, 1))
        self.assertTrue(options['Hecho']['url'].endswith('#tasks'))
        self.assertEqual(len(self.get(self.member, status='inventado').context['tasks']), 2)

    def test_recent_comments_are_limited_to_four(self):
        for number in range(6):
            Comment.objects.create(task=self.task, author=self.leader, content=f'Comentario {number}')
        self.assertEqual(len(self.get(self.member).context['comments']), 4)

    def test_deadline_card_for_an_overdue_project(self):
        project = make_project(
            self.leader, self.team, due_date=timezone.localdate() - timedelta(days=3),
        )
        card = self.get(self.leader, project).context['cards'][3]
        self.assertEqual((card['value'], card['alert']), (3, True))

    def test_client_sees_the_page_without_edit_controls(self):
        response = self.get(self.client_user)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('projects:update', args=[self.project.pk]))
        self.assertNotContains(response, reverse('tasks:create', args=[self.project.pk]))