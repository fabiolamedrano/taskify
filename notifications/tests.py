from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import WorldMixin, make_task

from .models import Notification


class NotificationViewTests(WorldMixin, TestCase):
    def setUp(self):
        self.note = Notification.objects.create(
            user=self.member, task=self.task, type=Notification.Type.COMMENT, message='Hola',
        )

    def test_opening_marks_as_read_and_goes_to_the_task(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('notifications:open', args=[self.note.pk]))
        self.assertRedirects(response, self.task.get_absolute_url())
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_read)

    def test_cannot_open_someone_elses_notification(self):
        self.client.force_login(self.leader)
        response = self.client.post(reverse('notifications:open', args=[self.note.pk]))
        self.assertEqual(response.status_code, 404)
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_read)

    def test_falls_back_to_the_list_when_the_task_is_not_visible(self):
        note = Notification.objects.create(
            user=self.outsider, task=self.task, type=Notification.Type.COMMENT, message='Ya no',
        )
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('notifications:open', args=[note.pk]))
        self.assertRedirects(response, reverse('notifications:list'))

    def test_mark_all_read_only_redirects_to_safe_urls(self):
        self.client.force_login(self.member)
        url = reverse('notifications:read_all')
        response = self.client.post(url, {'next': 'https://evil.example/'})
        self.assertRedirects(response, reverse('notifications:list'))
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_read)

        response = self.client.post(url, {'next': '/'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_unread_counter_and_filter(self):
        Notification.objects.create(
            user=self.member, type=Notification.Type.COMMENT, message='Leída', is_read=True,
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse('notifications:list'), {'filter': 'unread'})
        self.assertEqual(response.context['unread_notifications_count'], 1)
        self.assertEqual(len(response.context['notifications']), 1)


class DueNotificationCommandTests(WorldMixin, TestCase):
    def run_command(self):
        call_command('notify_due_tasks', stdout=StringIO())

    def test_one_notification_per_task_per_day(self):
        today = timezone.localdate()
        due = make_task(self.project, assigned_user=self.member, due_date=today)
        late = make_task(self.project, assigned_user=self.member, due_date=today - timedelta(days=3))
        make_task(self.project, assigned_user=self.member, due_date=today + timedelta(days=30))
        make_task(self.project, assigned_user=self.member, due_date=today, status='done')
        make_task(self.project, due_date=today)  # sin responsable

        self.run_command()
        notifications = Notification.objects.filter(type=Notification.Type.DUE_DATE)
        print('ESPERADAS:', due.pk, late.pk)
        print('CREADAS:', list(notifications.values_list('task_id', 'message')))
        self.assertEqual(set(notifications.values_list('task_id', flat=True)), {due.pk, late.pk})
        self.assertTrue(notifications.get(task=due).message.startswith('Vence hoy'))
        self.assertTrue(notifications.get(task=late).message.startswith('Vencida'))

        self.run_command()
        self.assertEqual(notifications.count(), 2)