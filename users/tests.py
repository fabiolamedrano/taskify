import os
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.factories import PASSWORD, TempMediaMixin, WorldMixin, make_user

User = get_user_model()
STRONG_PASSWORD = 'Clave-segura-2026'

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

def image_file(name='avatar.png'):
    buffer = BytesIO()
    Image.new('RGB', (8, 8), 'purple').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class SignupTests(WorldMixin, TestCase):
    def payload(self, **extra):
        data = {
            'username': 'nuevo', 'email': 'nuevo@test.local',
            'first_name': 'Nuevo', 'last_name': 'Usuario',
            'password1': STRONG_PASSWORD, 'password2': STRONG_PASSWORD,
        }
        data.update(extra)
        return data

    def test_signup_creates_a_member_and_logs_in(self):
        response = self.client.post(reverse('signup'), self.payload())
        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(username='nuevo')
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_privileged_fields_in_the_request_are_ignored(self):
        self.client.post(
            reverse('signup'), self.payload(role='admin', is_staff='on', is_superuser='on'),
        )
        user = User.objects.get(username='nuevo')
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_invalid_data_is_rejected(self):
        before = User.objects.count()
        self.client.post(reverse('signup'), self.payload(email=self.member.email.upper()))
        self.client.post(reverse('signup'), self.payload(password1='12345678', password2='12345678'))
        self.client.post(reverse('signup'), self.payload(password2='otra-clave-2026'))
        self.assertEqual(User.objects.count(), before)

    @override_settings(ALLOW_SIGNUP=False)
    def test_signup_can_be_turned_off(self):
        self.assertEqual(self.client.get(reverse('signup')).status_code, 404)
        self.assertEqual(self.client.post(reverse('signup'), self.payload()).status_code, 404)
        self.assertFalse(User.objects.filter(username='nuevo').exists())
        self.assertNotContains(self.client.get(reverse('login')), reverse('signup'))

    def test_login_links_to_signup_and_logged_in_users_are_redirected(self):
        self.assertContains(self.client.get(reverse('login')), reverse('signup'))
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse('signup')), reverse('dashboard'))


class ProfileTests(TempMediaMixin, WorldMixin, TestCase):
    def payload(self, **extra):
        data = {'first_name': 'Nuevo', 'last_name': 'Nombre', 'email': 'Nuevo.Correo@Test.local'}
        data.update(extra)
        return data

    def post(self, **extra):
        return self.client.post(reverse('users:profile'), self.payload(**extra))

    def test_login_is_required(self):
        response = self.client.get(reverse('users:profile'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('users:profile')}")

    def test_user_updates_own_data_but_not_role_or_username(self):
        self.client.force_login(self.member)
        response = self.post(role='admin', username='otro', is_superuser='on')
        self.assertRedirects(response, reverse('users:profile'))
        self.member.refresh_from_db()
        self.assertEqual((self.member.first_name, self.member.email), ('Nuevo', 'nuevo.correo@test.local'))
        self.assertEqual((self.member.username, self.member.role), ('member', User.Role.MEMBER))
        self.assertFalse(self.member.is_superuser)

    def test_clients_can_edit_their_own_profile(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse('users:profile')).status_code, 200)
        self.assertRedirects(self.post(), reverse('users:profile'))

    def test_duplicate_email_is_rejected(self):
        self.client.force_login(self.member)
        response = self.post(email=self.leader.email.upper())
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, 'member@test.local')

    def test_avatar_upload_replace_and_remove_clean_up_files(self):
        self.client.force_login(self.member)
        self.post(avatar=image_file('uno.png'))
        self.member.refresh_from_db()
        first = self.member.avatar.path
        self.assertTrue(os.path.exists(first))

        self.post(avatar=image_file('dos.png'))
        self.member.refresh_from_db()
        second = self.member.avatar.path
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(first))
        self.assertTrue(os.path.exists(second))

        self.post(remove_avatar='on')
        self.member.refresh_from_db()
        self.assertFalse(self.member.avatar)
        self.assertFalse(os.path.exists(second))

    def test_invalid_avatar_is_rejected(self):
        self.client.force_login(self.member)
        fake = SimpleUploadedFile('avatar.png', b'no soy una imagen', content_type='image/png')
        self.post(avatar=fake)
        self.member.refresh_from_db()
        self.assertFalse(self.member.avatar)


class PasswordChangeTests(WorldMixin, TestCase):
    def change(self, **extra):
        data = {
            'old_password': PASSWORD,
            'new_password1': STRONG_PASSWORD, 'new_password2': STRONG_PASSWORD,
        }
        data.update(extra)
        return self.client.post(reverse('users:password_change'), data)

    def test_login_is_required(self):
        response = self.client.get(reverse('users:password_change'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('users:password_change')}")

    def test_password_is_changed_and_the_session_survives(self):
        self.client.force_login(self.member)
        self.assertRedirects(self.change(), reverse('users:profile'))
        self.assertEqual(self.client.get(reverse('users:profile')).status_code, 200)
        self.client.logout()
        self.assertTrue(self.client.login(username=self.member.username, password=STRONG_PASSWORD))

    def test_wrong_current_password_or_weak_new_one_is_rejected(self):
        self.client.force_login(self.member)
        self.change(old_password='incorrecta')
        self.change(new_password1='12345678', new_password2='12345678')
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(PASSWORD))

class UserListRedesignTests(WorldMixin, TestCase):
    def setUp(self):
        super().setUp()
        make_user(is_active=False)

    def context(self, **params):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:list'), params)
        
        self.assertEqual(
            response.status_code, 200, 
            f"La vista falló con código {response.status_code} en vez de 200."
        )
        
        return response.context_data

    def test_cards_count_everyone_by_role(self):
        cards = self.context()['cards']
        self.assertEqual([card['value'] for card in cards], [6, 1, 4, 1])
        self.assertEqual(cards[0]['caption'], '1 inactivo')

    def test_chip_counts_respect_the_other_filter(self):
        context = self.context(role='member')
        roles = {option['label']: option for option in context['role_options']}
        self.assertEqual((roles['Todos']['count'], roles['Miembro']['count']), (6, 4))
        active = {option['label']: option for option in context['active_options']}
        self.assertEqual((active['Activos']['count'], active['Inactivos']['count']), (3, 1))
        self.assertEqual(len(context['users']), 4)

    def test_search_filters_and_hidden_params_keep_the_filters(self):
        context = self.context(q='leader', role='member')
        self.assertEqual([user.username for user in context['users']], ['leader'])
        self.assertEqual(context['hidden_params'], [('role', 'member')])
        self.assertTrue(context['has_filters'])

    def test_invalid_filters_are_ignored(self):
        context = self.context(role='inventado', active='quizá')
        self.assertEqual(len(context['users']), 6)
        self.assertFalse(context['has_filters'])
