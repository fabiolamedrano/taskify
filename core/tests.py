from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import WorldMixin, make_task, make_user
from projects.models import Project
from notifications.models import Notification
from tasks.models import Task, TimeLog

User = get_user_model()


class DashboardTests(WorldMixin, TestCase):
    def test_login_is_required(self):
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)

    def test_stats_reflect_my_tasks(self):
        today = timezone.localdate()
        make_task(
            self.project, assigned_user=self.member,
            status=Task.Status.DOING, due_date=today + timedelta(days=2),
        )
        make_task(self.project, assigned_user=self.member, due_date=today - timedelta(days=1))
        self.client.force_login(self.member)
        stats = self.client.get(reverse('dashboard')).context['stats']
        self.assertEqual(stats['todo'], 2)
        self.assertEqual(stats['doing'], 1)
        self.assertEqual(stats['due_soon'], 1)
        self.assertEqual(stats['overdue'], 1)

    def test_hours_this_month(self):
        TimeLog.objects.create(task=self.task, user=self.member, date=timezone.localdate(), hours=3)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('dashboard')).context['month_hours'], Decimal('3'))

    def test_user_without_data_sees_empty_state(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['todo'], 0)


class SeedCommandTests(TestCase):
    def seed(self, *args):
        call_command('seed_data', *args, stdout=StringIO())

    def test_is_idempotent(self):
        self.seed()
        counts = (Task.objects.count(), User.objects.count(), Notification.objects.count())
        self.seed()
        self.assertEqual((Task.objects.count(), User.objects.count(), Notification.objects.count()), counts)
        self.assertEqual(Task.objects.count(), 12)
        self.assertEqual(User.objects.get(username='cliente').role, User.Role.CLIENT)

    def test_reset_reloads_the_same_data(self):
        self.seed()
        self.seed('--reset')
        self.assertEqual(Task.objects.count(), 12)

class DashboardChartsTests(WorldMixin, TestCase):
    def test_week_chart_and_donut(self):
        today = timezone.localdate()
        TimeLog.objects.create(task=self.task, user=self.member, date=today, hours=Decimal('4'))
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        self.client.force_login(self.member)
        context = self.client.get(reverse('dashboard')).context

        today_bar = [day for day in context['week']['days'] if day['is_today']][0]
        self.assertEqual(today_bar['total'], Decimal('4'))
        self.assertEqual(context['week']['total'], Decimal('4'))
        self.assertEqual(context['donut']['total'], 2)
        self.assertEqual(context['donut']['done_pct'], 50)

    def test_empty_donut(self):
        self.client.force_login(self.outsider)
        donut = self.client.get(reverse('dashboard')).context['donut']
        self.assertEqual(donut, {'total': 0, 'done_pct': 0, 'doing_end': 0})


class NavigationSectionTests(WorldMixin, TestCase):
    def section(self, name, *args):
        self.client.force_login(self.admin)
        return self.client.get(reverse(name, args=args)).context['nav_section']

    def test_sections_are_detected(self):
        self.assertEqual(self.section('dashboard'), 'dashboard')
        self.assertEqual(self.section('projects:detail', self.project.pk), 'projects')
        self.assertEqual(self.section('tasks:detail', self.task.pk), 'projects')
        self.assertEqual(self.section('tasks:mine'), 'mine')
        self.assertEqual(self.section('tasks:my_time'), 'my_time')
        self.assertEqual(self.section('teams:list'), 'teams')
        self.assertEqual(self.section('tags:list'), 'tags')

    def test_profile_pages_do_not_highlight_the_admin_users_link(self):
        self.assertEqual(self.section('users:profile'), 'profile')
        self.assertEqual(self.section('users:password_change'), 'profile')

class SeedBulkCommandTests(TestCase):
    def run_command(self, *args):
        call_command(
            'seed_bulk', '--users', '6', '--teams', '2', '--projects', '3', '--tasks', '5',
            *args, stdout=StringIO(),
        )

    def test_generates_data_refuses_duplicates_and_resets(self):
        self.run_command()
        self.assertEqual(User.objects.filter(username__startswith='demo_').count(), 8)
        self.assertEqual(Project.objects.count(), 3)
        self.assertGreaterEqual(Task.objects.count(), 15)

        with self.assertRaises(CommandError):
            self.run_command()

        self.run_command('--reset')
        self.assertEqual(Project.objects.count(), 3)
        self.assertEqual(User.objects.filter(username__startswith='demo_').count(), 8)