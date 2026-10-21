from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.factories import PASSWORD, WorldMixin

User = get_user_model()


class UserAdminTests(WorldMixin, TestCase):
    def test_only_admins_can_open_user_screens(self):
        for name in ('users:list', 'users:create'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)  # sin sesión
            for user in (self.member, self.client_user):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
            self.client.logout()

    def test_admin_creates_user_with_role_and_hashed_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('users:create'), {
            'username': 'nuevo', 'email': 'nuevo@test.local',
            'first_name': 'Nuevo', 'last_name': 'Usuario', 'role': 'client',
            'password1': 'Clave-segura-2026', 'password2': 'Clave-segura-2026',
        })
        self.assertRedirects(response, reverse('users:list'))
        user = User.objects.get(username='nuevo')
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertNotEqual(user.password, 'Clave-segura-2026')
        self.assertTrue(user.check_password('Clave-segura-2026'))

    def test_duplicate_email_is_rejected(self):
        self.client.force_login(self.admin)
        before = User.objects.count()
        self.client.post(reverse('users:create'), {
            'username': 'otro', 'email': self.member.email, 'role': 'member',
            'password1': 'Clave-segura-2026', 'password2': 'Clave-segura-2026',
        })
        self.assertEqual(User.objects.count(), before)

    def test_admin_cannot_change_own_role_or_deactivate_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('users:update', args=[self.admin.pk]), {
            'username': self.admin.username, 'email': self.admin.email, 'role': 'member',
        })  # sin is_active: equivale a desmarcar la casilla
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)
        self.assertTrue(self.admin.is_active)

    def test_deactivated_user_cannot_log_in(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('users:update', args=[self.member.pk]), {
            'username': self.member.username, 'email': self.member.email, 'role': 'member',
        })
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.client.logout()
        self.assertFalse(self.client.login(username=self.member.username, password=PASSWORD))