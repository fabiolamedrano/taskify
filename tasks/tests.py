import os
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import TempMediaMixin, WorldMixin, make_task
from notifications.models import Notification

from .models import Attachment, Comment, Subtask, Tag, Task, TimeLog


class ConstraintTests(WorldMixin, TestCase):
    def test_timelog_hours_must_be_between_0_and_24(self):
        for hours in ('0', '-1', '24.01'):
            with self.assertRaises(IntegrityError), transaction.atomic():
                TimeLog.objects.create(
                    task=self.task, user=self.member,
                    date=timezone.localdate(), hours=Decimal(hours),
                )

    def test_task_due_date_cannot_precede_start_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_task(self.project, start_date=date(2026, 10, 10), due_date=date(2026, 10, 1))


class BoardTests(WorldMixin, TestCase):
    def test_tasks_are_grouped_by_status(self):
        make_task(self.project, status=Task.Status.DONE)
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:board', args=[self.project.pk]))
        columns = {value: tasks for value, _, tasks in response.context['columns']}
        self.assertEqual(len(columns['todo']), 1)
        self.assertEqual(len(columns['doing']), 0)
        self.assertEqual(len(columns['done']), 1)

    def test_client_sees_board_as_read_only(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('tasks:board', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_move'])

    def test_hidden_board_returns_404(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:board', args=[self.hidden_project.pk]))
        self.assertEqual(response.status_code, 404)


class TaskCrudTests(WorldMixin, TestCase):
    def data(self, **extra):
        data = {'title': 'Nueva', 'priority': 'high', 'status': 'todo'}
        data.update(extra)
        return data

    def test_creating_task_notifies_assignee(self):
        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('tasks:create', args=[self.project.pk]),
            self.data(assigned_user=self.member.pk),
        )
        task = Task.objects.get(title='Nueva')
        self.assertRedirects(response, task.get_absolute_url())
        self.assertEqual(task.creator, self.leader)
        self.assertEqual(task.project, self.project)
        self.assertTrue(Notification.objects.filter(
            user=self.member, task=task, type=Notification.Type.ASSIGNMENT,
        ).exists())

    def test_self_assignment_does_not_notify(self):
        self.client.force_login(self.leader)
        self.client.post(
            reverse('tasks:create', args=[self.project.pk]),
            self.data(assigned_user=self.leader.pk),
        )
        self.assertTrue(Task.objects.filter(title='Nueva').exists())
        self.assertFalse(Notification.objects.exists())

    def test_cannot_assign_to_someone_outside_the_project(self):
        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('tasks:create', args=[self.project.pk]),
            self.data(assigned_user=self.outsider.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title='Nueva').exists())

    def test_client_cannot_create_tasks(self):
        self.client.force_login(self.client_user)
        url = reverse('tasks:create', args=[self.project.pk])
        self.assertEqual(self.client.post(url, self.data()).status_code, 403)
        self.assertFalse(Task.objects.filter(title='Nueva').exists())

    def test_cannot_create_task_in_hidden_project(self):
        self.client.force_login(self.member)
        url = reverse('tasks:create', args=[self.hidden_project.pk])
        self.assertEqual(self.client.post(url, self.data()).status_code, 404)

    def test_status_is_preselected_from_query_string(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:create', args=[self.project.pk]), {'status': 'doing'})
        self.assertEqual(response.context['form'].initial['status'], 'doing')

    def test_changing_assignee_notifies_the_new_one(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('tasks:update', args=[self.task.pk]),
            self.data(title=self.task.title, assigned_user=self.leader.pk),
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.assigned_user, self.leader)
        self.assertTrue(Notification.objects.filter(user=self.leader, task=self.task).exists())

    def test_client_cannot_edit_tasks(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse('tasks:update', args=[self.task.pk])).status_code, 403)

    def test_only_creator_or_admin_can_delete(self):
        url = reverse('tasks:delete', args=[self.task.pk])
        self.client.force_login(self.member)  # está asignado, pero no la creó
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

        self.client.force_login(self.leader)
        self.assertRedirects(self.client.post(url), reverse('tasks:board', args=[self.project.pk]))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())


class SubtaskTests(WorldMixin, TestCase):
    def test_subtasks_get_consecutive_order(self):
        self.client.force_login(self.member)
        url = reverse('tasks:subtask_add', args=[self.task.pk])
        self.client.post(url, {'title': 'Uno'})
        self.client.post(url, {'title': 'Dos'})
        self.assertEqual(
            list(self.task.subtasks.values_list('title', 'order')), [('Uno', 0), ('Dos', 1)],
        )

    def test_toggle_flips_completion_but_not_for_clients(self):
        subtask = Subtask.objects.create(task=self.task, title='X')
        url = reverse('tasks:subtask_toggle', args=[subtask.pk])
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.member)
        self.client.post(url)
        subtask.refresh_from_db()
        self.assertTrue(subtask.is_completed)

    def test_client_cannot_add_or_delete_subtasks(self):
        subtask = Subtask.objects.create(task=self.task, title='X')
        self.client.force_login(self.client_user)
        self.assertEqual(
            self.client.post(reverse('tasks:subtask_add', args=[self.task.pk]), {'title': 'Y'}).status_code, 403,
        )
        self.assertEqual(
            self.client.post(reverse('tasks:subtask_delete', args=[subtask.pk])).status_code, 403,
        )
        self.assertEqual(self.task.subtasks.count(), 1)


class CommentTests(WorldMixin, TestCase):
    def post_comment(self, content='Hola'):
        return self.client.post(reverse('tasks:comment_add', args=[self.task.pk]), {'content': content})

    def test_comment_notifies_the_assignee(self):
        self.client.force_login(self.leader)
        self.post_comment()
        self.assertEqual(Comment.objects.filter(task=self.task).count(), 1)
        notification = Notification.objects.get(user=self.member)
        self.assertEqual(notification.type, Notification.Type.COMMENT)
        self.assertEqual(notification.task, self.task)

    def test_comment_by_the_assignee_does_not_notify(self):
        self.client.force_login(self.member)
        self.post_comment()
        self.assertEqual(Comment.objects.count(), 1)
        self.assertFalse(Notification.objects.exists())

    def test_empty_comment_is_rejected(self):
        self.client.force_login(self.member)
        self.post_comment('')
        self.assertFalse(Comment.objects.exists())

    def test_client_cannot_comment(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.post_comment().status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_cannot_comment_on_hidden_task(self):
        self.client.force_login(self.member)
        url = reverse('tasks:comment_add', args=[self.hidden_task.pk])
        self.assertEqual(self.client.post(url, {'content': 'Hola'}).status_code, 404)

    def test_only_author_or_admin_can_delete_comment(self):
        comment = Comment.objects.create(task=self.task, author=self.member, content='Mío')
        url = reverse('tasks:comment_delete', args=[comment.pk])
        self.client.force_login(self.leader)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())


class TimeLogFormTests(WorldMixin, TestCase):
    def post_time(self, **data):
        payload = {'date': timezone.localdate().isoformat(), 'hours': '2', 'description': 'Trabajo'}
        payload.update(data)
        return self.client.post(reverse('tasks:timelog_add', args=[self.task.pk]), payload)

    def test_valid_entry_is_saved_for_the_current_user(self):
        self.client.force_login(self.member)
        response = self.post_time()
        self.assertRedirects(
            response, f"{reverse('tasks:detail', args=[self.task.pk])}#time",
            fetch_redirect_response=False,
        )
        log = TimeLog.objects.get()
        self.assertEqual(log.user, self.member)
        self.assertEqual(log.hours, Decimal('2'))

    def test_invalid_hours_and_future_dates_are_rejected(self):
        self.client.force_login(self.member)
        self.post_time(hours='0')
        self.post_time(hours='25')
        self.post_time(date=(timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertFalse(TimeLog.objects.exists())

    def test_client_cannot_log_time(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.post_time().status_code, 403)
        self.assertFalse(TimeLog.objects.exists())


class AttachmentTests(TempMediaMixin, WorldMixin, TestCase):
    def post_attachment(self, **data):
        return self.client.post(reverse('tasks:attachment_add', args=[self.task.pk]), data)

    def pdf(self, name='informe.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4 contenido', content_type='application/pdf')

    def test_allowed_file_is_uploaded(self):
        self.client.force_login(self.member)
        self.post_attachment(file=self.pdf())
        attachment = Attachment.objects.get(task=self.task)
        self.assertEqual(attachment.type, Attachment.Type.DOCUMENT)
        self.assertEqual(attachment.file_name, 'informe.pdf')
        self.assertEqual(attachment.uploaded_by, self.member)
        self.assertEqual(attachment.size_kb, 1)

    def test_images_are_detected(self):
        self.client.force_login(self.member)
        image = SimpleUploadedFile('foto.png', b'\x89PNG\r\n', content_type='image/png')
        self.post_attachment(file=image)
        self.assertEqual(Attachment.objects.get().type, Attachment.Type.IMAGE)

    def test_forbidden_extension_is_rejected(self):
        self.client.force_login(self.member)
        exe = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
        self.post_attachment(file=exe)
        self.assertFalse(Attachment.objects.exists())

    def test_oversized_file_is_rejected(self):
        self.client.force_login(self.member)
        big = SimpleUploadedFile('grande.pdf', b'0' * (5 * 1024 * 1024 + 1), content_type='application/pdf')
        self.post_attachment(file=big)
        self.assertFalse(Attachment.objects.exists())

    def test_link_is_saved_as_link(self):
        self.client.force_login(self.member)
        self.post_attachment(url='https://example.com/doc')
        attachment = Attachment.objects.get()
        self.assertEqual(attachment.type, Attachment.Type.LINK)
        self.assertEqual(attachment.file_name, 'https://example.com/doc')

    def test_requires_a_file_or_a_link_but_not_both(self):
        self.client.force_login(self.member)
        self.post_attachment()
        self.post_attachment(file=self.pdf(), url='https://example.com')
        self.assertFalse(Attachment.objects.exists())

    def test_deleting_attachment_removes_the_file_from_disk(self):
        self.client.force_login(self.member)
        self.post_attachment(file=self.pdf())
        attachment = Attachment.objects.get()
        path = attachment.file.path
        self.assertTrue(os.path.exists(path))
        self.client.post(reverse('tasks:attachment_delete', args=[attachment.pk]))
        self.assertFalse(os.path.exists(path))
        self.assertFalse(Attachment.objects.exists())


class MyTasksTests(WorldMixin, TestCase):
    def shown(self, response):
        return [task for group in response.context['groups'] for task in group['tasks']]

    def test_lists_only_my_open_tasks(self):
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        make_task(self.project, assigned_user=self.leader)
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:mine'))
        self.assertEqual(self.shown(response), [self.task])

    def test_all_filter_includes_done_and_invalid_filters_fall_back(self):
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:mine'), {'status': 'all'})
        self.assertEqual(response.context['total'], 2)
        response = self.client.get(reverse('tasks:mine'), {'status': 'xx', 'priority': 'yy'})
        self.assertEqual(response.context['total'], 1)

    def test_overdue_tasks_are_counted(self):
        make_task(
            self.project, assigned_user=self.member,
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:mine'))
        self.assertEqual(response.context['overdue_count'], 1)


class MyTimeTests(WorldMixin, TestCase):
    def test_invalid_week_falls_back_to_the_current_week(self):
        self.client.force_login(self.member)
        for value in ('abc', '0001-01-01', '9999-12-31', ''):
            response = self.client.get(reverse('tasks:my_time'), {'week': value})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['is_current_week'])

    def test_weekly_totals(self):
        today = timezone.localdate()
        TimeLog.objects.create(task=self.task, user=self.member, date=today, hours=Decimal('2.5'))
        TimeLog.objects.create(task=self.task, user=self.member, date=today, hours=Decimal('1'))
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:my_time'))
        self.assertEqual(response.context['week_total'], Decimal('3.5'))
        self.assertEqual(response.context['days_logged'], 1)

    def test_quick_form_offers_only_my_open_tasks_and_validates(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:my_time'))
        queryset = response.context['quick_form'].fields['task'].queryset
        self.assertEqual(list(queryset), [self.task])

        url = reverse('tasks:my_time_add')
        today = timezone.localdate().isoformat()
        self.client.post(url, {'task': self.task.pk, 'date': today, 'hours': '30'})
        self.assertFalse(TimeLog.objects.exists())
        self.client.post(url, {'task': self.task.pk, 'date': today, 'hours': '2'})
        self.assertEqual(TimeLog.objects.count(), 1)

    def test_cannot_delete_someone_elses_log(self):
        log = TimeLog.objects.create(
            task=self.task, user=self.member, date=timezone.localdate(), hours=1,
        )
        url = reverse('tasks:my_time_delete', args=[log.pk])
        self.client.force_login(self.leader)  # ve la tarea, pero no es el autor
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(TimeLog.objects.filter(pk=log.pk).exists())
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(TimeLog.objects.filter(pk=log.pk).exists())

class TagManagementTests(WorldMixin, TestCase):
    def test_only_admins_can_manage_tags(self):
        self.assertEqual(self.client.get(reverse('tags:list')).status_code, 302)  # sin sesión
        for user in (self.member, self.client_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('tags:list')).status_code, 403)
            response = self.client.post(reverse('tags:create'), {'name': 'X', 'color': '#111111'})
            self.assertEqual(response.status_code, 403)
        self.assertFalse(Tag.objects.exists())

    def test_admin_creates_tag_and_color_is_normalized(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('tags:create'), {'name': 'Bug', 'color': '#ff0000'})
        self.assertRedirects(response, reverse('tags:list'))
        self.assertEqual(Tag.objects.get(name='Bug').color, '#FF0000')

    def test_invalid_color_and_duplicate_name_are_rejected(self):
        Tag.objects.create(name='Bug', color='#111111')
        self.client.force_login(self.admin)
        self.client.post(reverse('tags:create'), {'name': 'Bug', 'color': '#222222'})
        self.client.post(reverse('tags:create'), {'name': 'Otra', 'color': 'rojo'})
        self.assertEqual(Tag.objects.count(), 1)

    def test_admin_edits_tag(self):
        tag = Tag.objects.create(name='Viejo', color='#111111')
        self.client.force_login(self.admin)
        self.client.post(reverse('tags:update', args=[tag.pk]), {'name': 'Nuevo', 'color': '#00ff00'})
        tag.refresh_from_db()
        self.assertEqual((tag.name, tag.color), ('Nuevo', '#00FF00'))

    def test_deleting_a_tag_keeps_its_tasks(self):
        tag = Tag.objects.create(name='Temporal', color='#111111')
        self.task.tags.add(tag)
        self.client.force_login(self.admin)
        url = reverse('tags:delete', args=[tag.pk])
        self.assertEqual(self.client.get(url).status_code, 405)  # solo POST
        self.assertRedirects(self.client.post(url), reverse('tags:list'))
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

class MyTasksBoardTests(WorldMixin, TestCase):
    def get(self, **params):
        self.client.force_login(self.member)
        return self.client.get(reverse('tasks:mine'), params)

    def shown(self, response):
        return [task for group in response.context['groups'] for task in group['tasks']]

    def columns(self, response):
        return {value: tasks for value, _, tasks in response.context['columns']}

    def test_board_groups_tasks_by_status(self):
        make_task(self.project, assigned_user=self.member, status=Task.Status.DOING)
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        columns = self.columns(self.get(view='board'))
        self.assertEqual([len(columns[s]) for s in ('todo', 'doing', 'done')], [1, 1, 1])

    def test_done_column_is_limited_to_the_most_recent(self):
        for _ in range(10):
            make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        response = self.get(view='board')
        self.assertEqual(len(self.columns(response)['done']), 8)
        self.assertEqual(response.context['done_hidden'], 2)

    def test_cards_use_the_api_and_show_subtask_progress(self):
        Subtask.objects.create(task=self.task, title='A', is_completed=True)
        Subtask.objects.create(task=self.task, title='B')
        response = self.get(view='board')
        self.assertContains(response, reverse('api:task-detail', args=[self.task.pk]))
        card = self.columns(response)['todo'][0]
        self.assertEqual((card.subtask_total, card.subtask_done, card.subtask_percent), (2, 1, 50))

    def test_due_filter(self):
        today = timezone.localdate()
        late = make_task(self.project, assigned_user=self.member, due_date=today - timedelta(days=1))
        soon = make_task(self.project, assigned_user=self.member, due_date=today + timedelta(days=3))
        make_task(self.project, assigned_user=self.member, due_date=today + timedelta(days=30))
        self.assertEqual(self.shown(self.get(due='overdue')), [late])
        self.assertEqual(self.shown(self.get(due='week')), [soon])
        self.assertEqual(len(self.shown(self.get(due='inventado'))), 4)

    def test_stats_ignore_the_filters(self):
        make_task(self.project, assigned_user=self.member, status=Task.Status.DONE)
        context = self.get(priority='high').context
        self.assertEqual(context['total'], 0)
        self.assertEqual((context['stats']['open'], context['stats']['done']), (1, 1))

    def test_view_toggle_and_search_keep_the_other_filters(self):
        context = self.get(view='board', priority='high', q='x').context
        options = {option['label']: option for option in context['view_options']}
        self.assertTrue(options['Tablero']['active'])
        self.assertNotIn('view=board', options['Lista']['url'])
        self.assertIn('priority=high', options['Lista']['url'])
        self.assertEqual(sorted(context['hidden_params']), [('priority', 'high'), ('view', 'board')])
        self.assertTrue(context['has_filters'])

    def test_client_gets_a_read_only_board(self):
        make_task(self.project, assigned_user=self.client_user)
        self.client.force_login(self.client_user)
        context = self.client.get(reverse('tasks:mine'), {'view': 'board'}).context
        self.assertFalse(context['can_move'])

class ProjectBoardRedesignTests(WorldMixin, TestCase):
    def get(self, user=None, **params):
        self.client.force_login(user or self.member)
        return self.client.get(reverse('tasks:board', args=[self.project.pk]), params)

    def cards(self, response):
        return [task for _, _, tasks in response.context['columns'] for task in tasks]

    def test_assignment_filter(self):
        free = make_task(self.project, title='Libre')
        make_task(self.project, title='Ajena', assigned_user=self.leader)
        self.assertEqual(self.cards(self.get(assigned='mine')), [self.task])
        self.assertEqual(self.cards(self.get(assigned='none')), [free])
        self.assertEqual(len(self.cards(self.get(assigned='inventado'))), 3)

    def test_priority_filter_and_filters_flag(self):
        high = make_task(self.project, priority=Task.Priority.HIGH)
        response = self.get(priority='high')
        self.assertEqual(self.cards(response), [high])
        self.assertTrue(response.context['has_filters'])
        self.assertFalse(self.get().context['has_filters'])

    def test_done_column_is_limited_to_the_most_recent(self):
        for _ in range(14):
            make_task(self.project, status=Task.Status.DONE)
        response = self.get()
        columns = {value: tasks for value, _, tasks in response.context['columns']}
        self.assertEqual((len(columns['done']), response.context['done_hidden']), (12, 2))
        self.assertContains(response, '?status=done#tasks')

    def test_cards_use_the_api_and_show_the_assignee(self):
        make_task(self.project, title='Libre')
        response = self.get()
        self.assertContains(response, reverse('api:task-detail', args=[self.task.pk]))
        self.assertContains(response, 'Sin asignar')

    def test_cards_show_subtask_progress(self):
        Subtask.objects.create(task=self.task, title='A', is_completed=True)
        Subtask.objects.create(task=self.task, title='B')
        card = self.cards(self.get())[0]
        self.assertEqual((card.subtask_total, card.subtask_done, card.subtask_percent), (2, 1, 50))

class TaskDetailRedesignTests(WorldMixin, TestCase):
    def get(self, user=None, task=None):
        self.client.force_login(user or self.member)
        return self.client.get(reverse('tasks:detail', args=[(task or self.task).pk]))

    def test_cards_summarize_subtasks_hours_and_comments(self):
        Subtask.objects.create(task=self.task, title='A', is_completed=True)
        Subtask.objects.create(task=self.task, title='B')
        TimeLog.objects.create(
            task=self.task, user=self.member, date=timezone.localdate(), hours=Decimal('2.5'),
        )
        Comment.objects.create(task=self.task, author=self.leader, content='Hola')
        cards = self.get().context['cards']
        self.assertEqual((cards[0]['value'], cards[0]['caption']), (50, '1 de 2 subtareas'))
        self.assertEqual((cards[1]['value'], cards[1]['caption']), ('2.5', 'Sin estimación'))
        self.assertEqual(cards[3]['value'], 1)

    def test_cards_for_a_task_without_data(self):
        cards = self.get().context['cards']
        self.assertEqual((cards[0]['value'], cards[0]['caption']), ('—', 'Sin subtareas'))
        self.assertEqual(cards[1]['value'], '0')
        self.assertEqual(cards[2]['value'], '—')

    def test_deadline_card_states(self):
        today = timezone.localdate()
        cases = [
            (today - timedelta(days=2), Task.Status.TODO, 2, True),
            (today, Task.Status.TODO, 'Hoy', False),
            (today + timedelta(days=5), Task.Status.TODO, 5, False),
            (today - timedelta(days=2), Task.Status.DONE, 'Hecha', False),
        ]
        for due, status, value, alert in cases:
            task = make_task(self.project, due_date=due, status=status)
            card = self.get(task=task).context['cards'][2]
            self.assertEqual((card['value'], card['alert']), (value, alert))

    def test_time_is_broken_down_by_person(self):
        today = timezone.localdate()
        TimeLog.objects.create(task=self.task, user=self.member, date=today, hours=3)
        TimeLog.objects.create(task=self.task, user=self.leader, date=today, hours=1)
        rows = self.get().context['time_by_person']
        self.assertEqual([(row['name'], row['percent']) for row in rows], [('member', 75), ('leader', 25)])

    def test_the_page_offers_the_status_switch_and_respects_read_only(self):
        response = self.get()
        self.assertContains(response, 'id="status-switch"')
        self.assertContains(response, reverse('api:task-detail', args=[self.task.pk]))
        read_only = self.get(self.client_user)
        self.assertFalse(read_only.context['can_edit'])
        self.assertContains(read_only, 'Solo lectura')