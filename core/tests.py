import re
from pathlib import Path

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.views.defaults import server_error
from django.conf import settings
from django.template import Context, Template
from django.template.loader import render_to_string

from core.factories import WorldMixin, make_task, make_user
from projects.models import Project
from notifications.models import Notification
from tasks.models import Tag, Task, TimeLog

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

class FormPagesRenderTests(WorldMixin, TestCase):
    def test_every_form_and_confirmation_page_renders_for_an_admin(self):
        tag = Tag.objects.create(name='Etiqueta', color='#112233')
        self.client.force_login(self.admin)
        pages = [
            reverse('projects:create'), reverse('projects:update', args=[self.project.pk]),
            reverse('projects:delete', args=[self.project.pk]),
            reverse('tasks:create', args=[self.project.pk]), reverse('tasks:update', args=[self.task.pk]),
            reverse('tasks:delete', args=[self.task.pk]),
            reverse('teams:create'), reverse('teams:update', args=[self.team.pk]),
            reverse('teams:delete', args=[self.team.pk]),
            reverse('tags:list'), reverse('tags:create'), reverse('tags:update', args=[tag.pk]),
            reverse('users:list'), reverse('users:create'), reverse('users:update', args=[self.member.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_headings_and_buttons_come_from_each_page(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('projects:create')), 'Crear proyecto')
        self.assertContains(
            self.client.get(reverse('projects:update', args=[self.project.pk])), 'Guardar cambios',
        )
        self.assertContains(self.client.get(reverse('tags:create')), 'Crear etiqueta')
        self.assertContains(
            self.client.get(reverse('users:update', args=[self.member.pk])), 'multipart/form-data',
        )

class ErrorPagesTests(WorldMixin, TestCase):
    def test_404_page_for_a_missing_url(self):
        response = self.client.get('/esta/pagina/no/existe/')
        self.assertContains(response, 'Página no encontrada', status_code=404)
        self.assertTemplateUsed(response, '404.html')

    def test_a_hidden_project_shows_the_404_page(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('projects:detail', args=[self.hidden_project.pk]))
        self.assertContains(response, 'o no tienes acceso a ella', status_code=404)

    def test_403_page_when_permission_is_missing(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('users:list'))
        self.assertContains(response, 'No tienes permiso', status_code=403)
        self.assertTemplateUsed(response, '403.html')

    def test_expired_form_shows_its_own_403_page(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('login'), {'username': 'x', 'password': 'y'})
        self.assertContains(response, 'La página caducó', status_code=403)
        self.assertTemplateUsed(response, '403_csrf.html')

    def test_500_page_renders_without_a_session(self):
        response = server_error(RequestFactory().get('/'))
        self.assertEqual(response.status_code, 500)
        self.assertIn('Algo salió mal'.encode(), response.content)

class MobileNavigationBarTests(WorldMixin, TestCase):
    def test_bottom_bar_has_its_links_and_a_single_menu_button(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'aria-label="Navegación móvil"')
        for name in ('projects:list', 'tasks:mine', 'tasks:my_time'):
            self.assertContains(response, f'href="{reverse(name)}"')
        # Un id duplicado rompería el menú: el botón debe existir una sola vez
        self.assertContains(response, 'id="sidebar-toggle"', count=1)

    def test_every_main_page_renders_with_the_bar(self):
        self.client.force_login(self.admin)
        pages = [
            reverse('projects:list'), reverse('tasks:mine'), reverse('tasks:my_time'),
            reverse('teams:list'), reverse('notifications:list'), reverse('users:list'),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'Navegación móvil')

class ScrollContainerTests(TestCase):
    def test_table_scrollers_are_positioned(self):
        """Un .sr-only dentro de una tabla desplazable necesita un contenedor «relative»;
        si no, su posición estática ensancha toda la página en el móvil."""
        pattern = re.compile(r'<div class="([^"]*overflow-x-auto[^"]*)">\s*<table')
        checked = 0
        for path in Path(settings.BASE_DIR, 'templates').rglob('*.html'):
            for classes in pattern.findall(path.read_text(encoding='utf-8')):
                checked += 1
                self.assertIn('relative', classes.split(), f'{path.name}: falta "relative" en {classes!r}')
        self.assertGreaterEqual(checked, 3)

class StatCardTests(TestCase):
    def render(self, **extra):
        context = {'label': 'X', 'value': 1, 'caption': 'c', 'href': '/'}
        context.update(extra)
        return render_to_string('core/_stat_card.html', context)

    def test_dark_tone_and_alert_tint(self):
        self.assertIn('linear-gradient', self.render(dark=True))
        self.assertIn('bg-amber-50', self.render(tone='warm'))
        self.assertIn('bg-teal-50', self.render(tone='cool'))
        self.assertIn('bg-violet-50', self.render(tone='violet'))
        self.assertIn('bg-red-50', self.render(alert=True, value=2, tone='violet'))
        self.assertNotIn('bg-red-50', self.render(alert=True, value=0, tone='violet'))

    def test_tints_only_apply_on_mobile(self):
        self.assertIn('sm:bg-white', self.render(tone='warm'))

    def test_cards_in_a_loop_get_a_tone_by_position(self):
        template = Template(
            "{% for card in cards %}"
            "{% include 'core/_stat_card.html' with label=card href='/' value=1 caption='' %}"
            "{% endfor %}"
        )
        html = template.render(Context({'cards': ['a', 'b', 'c', 'd']}))
        self.assertEqual(
            (html.count('bg-amber-50'), html.count('bg-teal-50'), html.count('bg-violet-50')),
            (1, 1, 1),
        )


class SummaryGridTests(TestCase):
    def test_every_summary_grid_is_two_columns_on_mobile(self):
        found = 0
        for path in Path(settings.BASE_DIR, 'templates').rglob('*.html'):
            for classes in re.findall(r'aria-label="Resumen" class="([^"]*)"', path.read_text(encoding='utf-8')):
                found += 1
                self.assertIn('grid-cols-2', classes.split(), path.name)
                self.assertNotIn('grid-cols-1', classes.split(), path.name)
        self.assertEqual(found, 9)