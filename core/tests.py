from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import WorldMixin, make_task, make_user
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