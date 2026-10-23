from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.factories import WorldMixin, make_project, make_task, make_user
from tasks.models import Task

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