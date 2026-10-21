from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.factories import WorldMixin, make_task
from notifications.models import Notification
from projects.models import Project
from tasks.models import Comment, Task, TimeLog

User = get_user_model()


class APITestMixin(WorldMixin):
    def login(self, user):
        self.client.force_authenticate(user=user)

    def post(self, name, data, **kwargs):
        return self.client.post(reverse(name, **kwargs), data, format='json')


class AuthenticationTests(APITestMixin, APITestCase):
    def test_authentication_is_required(self):
        response = self.client.get(reverse('api:project-list'))
        self.assertIn(response.status_code, (401, 403))

    def test_clients_are_read_only(self):
        self.login(self.client_user)
        self.assertEqual(self.client.get(reverse('api:project-list')).status_code, 200)
        self.assertEqual(self.post('api:project-list', {'name': 'X'}).status_code, 403)
        response = self.client.patch(
            reverse('api:task-detail', args=[self.task.pk]), {'status': 'done'}, format='json',
        )
        self.assertEqual(response.status_code, 403)


class ProjectAPITests(APITestMixin, APITestCase):
    def test_list_only_returns_visible_projects(self):
        self.login(self.member)
        results = self.client.get(reverse('api:project-list')).json()['results']
        self.assertEqual([item['id'] for item in results], [self.project.pk])
        self.assertEqual(results[0]['task_count'], 1)

    def test_hidden_project_is_404(self):
        self.login(self.member)
        response = self.client.get(reverse('api:project-detail', args=[self.hidden_project.pk]))
        self.assertEqual(response.status_code, 404)

    def test_owner_comes_from_the_session_and_cannot_be_spoofed(self):
        self.login(self.member)
        response = self.post('api:project-list', {'name': 'API', 'status': 'active', 'owner': self.admin.pk})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Project.objects.get(name='API').owner, self.member)

    def test_validation_errors_return_400(self):
        self.login(self.member)
        response = self.post('api:project-list', {'name': 'X', 'budget': '-1'})
        self.assertEqual(response.status_code, 400)
        response = self.post('api:project-list', {
            'name': 'X', 'start_date': '2026-10-10', 'due_date': '2026-10-01',
        })
        self.assertEqual(response.status_code, 400)

    def test_only_owner_or_admin_can_delete(self):
        url = reverse('api:project-detail', args=[self.project.pk])
        self.login(self.member)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.login(self.leader)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())


class TaskAPITests(APITestMixin, APITestCase):
    def test_create_sets_the_creator(self):
        self.login(self.member)
        response = self.post('api:task-list', {'title': 'Desde la API', 'project': self.project.pk})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Task.objects.get(title='Desde la API').creator, self.member)

    def test_cannot_create_task_in_hidden_project(self):
        self.login(self.member)
        response = self.post('api:task-list', {'title': 'X', 'project': self.hidden_project.pk})
        self.assertEqual(response.status_code, 400)

    def test_date_order_is_validated(self):
        self.login(self.member)
        response = self.post('api:task-list', {
            'title': 'X', 'project': self.project.pk,
            'start_date': '2026-10-10', 'due_date': '2026-10-01',
        })
        self.assertEqual(response.status_code, 400)

    def test_patch_moves_a_task(self):
        self.login(self.member)
        response = self.client.patch(
            reverse('api:task-detail', args=[self.task.pk]), {'status': 'doing'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DOING)

    def test_filters(self):
        make_task(self.project, status=Task.Status.DONE, title='Terminada')
        self.login(self.member)
        results = self.client.get(reverse('api:task-list'), {'status': 'done'}).json()['results']
        self.assertEqual([item['title'] for item in results], ['Terminada'])

    def test_only_creator_or_admin_can_delete(self):
        url = reverse('api:task-detail', args=[self.task.pk])
        self.login(self.member)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.login(self.leader)
        self.assertEqual(self.client.delete(url).status_code, 204)


class RelatedResourcesAPITests(APITestMixin, APITestCase):
    def test_comment_author_comes_from_the_session(self):
        self.login(self.leader)
        response = self.post('api:comment-list', {'task': self.task.pk, 'content': 'Hola'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Comment.objects.get().author, self.leader)

    def test_cannot_comment_on_hidden_task(self):
        self.login(self.member)
        response = self.post('api:comment-list', {'task': self.hidden_task.pk, 'content': 'Hola'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_time_log_validation(self):
        self.login(self.member)
        today = timezone.localdate().isoformat()
        response = self.post('api:timelog-list', {'task': self.task.pk, 'date': today, 'hours': '30'})
        self.assertEqual(response.status_code, 400)
        response = self.post('api:timelog-list', {'task': self.task.pk, 'date': today, 'hours': '2.5'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TimeLog.objects.get().hours, Decimal('2.5'))

    def test_notifications_are_private(self):
        Notification.objects.create(user=self.member, type=Notification.Type.COMMENT, message='Privada')
        self.login(self.leader)
        self.assertEqual(self.client.get(reverse('api:notification-list')).json()['results'], [])

    def test_tags_are_admin_only_and_colors_are_validated(self):
        self.login(self.member)
        self.assertEqual(self.post('api:tag-list', {'name': 'X', 'color': '#112233'}).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.post('api:tag-list', {'name': 'Mal', 'color': 'rojo'}).status_code, 400)
        self.assertEqual(self.post('api:tag-list', {'name': 'Bien', 'color': '#112233'}).status_code, 201)


class UserAPITests(APITestMixin, APITestCase):
    def test_users_only_see_themselves_and_their_teams(self):
        self.login(self.outsider)
        results = self.client.get(reverse('api:user-list')).json()['results']
        self.assertEqual([item['id'] for item in results], [self.outsider.pk])

    def test_only_admins_can_create_users_and_passwords_are_hashed(self):
        data = {
            'username': 'creado', 'email': 'creado@test.local',
            'password': 'Clave-segura-2026', 'role': 'member',
        }
        self.login(self.member)
        self.assertEqual(self.post('api:user-list', data).status_code, 403)

        self.login(self.admin)
        response = self.post('api:user-list', data)
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('password', response.json())
        self.assertTrue(User.objects.get(username='creado').check_password('Clave-segura-2026'))