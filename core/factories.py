import shutil
import tempfile
from itertools import count

from django.contrib.auth import get_user_model
from django.test import override_settings

from projects.models import Project
from tasks.models import Task
from teams.models import Team, TeamMember

User = get_user_model()

PASSWORD = 'Clave-de-prueba-2026'
_sequence = count(1)


def make_user(role=User.Role.MEMBER, **extra):
    username = extra.pop('username', f'user{next(_sequence)}')
    return User.objects.create_user(
        username=username, email=f'{username}@test.local', password=PASSWORD, role=role, **extra,
    )


def make_team(leader=None, members=(), name=None):
    team = Team.objects.create(name=name or f'Equipo {next(_sequence)}', leader=leader)
    people = [leader, *members] if leader else list(members)
    for user in people:
        TeamMember.objects.get_or_create(team=team, user=user)
    return team


def make_project(owner, team=None, **extra):
    extra.setdefault('name', f'Proyecto {next(_sequence)}')
    return Project.objects.create(owner=owner, team=team, **extra)


def make_task(project, creator=None, **extra):
    extra.setdefault('title', f'Tarea {next(_sequence)}')
    return Task.objects.create(project=project, creator=creator or project.owner, **extra)


class WorldMixin:
    """Escenario compartido por las pruebas.

    - admin:       administrador
    - leader:      líder de `team` y propietario de `project`
    - member:      miembro de `team`, con `task` asignada
    - client_user: cliente que pertenece a `team` (solo lectura)
    - outsider:    sin relación con el equipo; dueño de `hidden_project`
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = make_user(User.Role.ADMIN, username='admin1')
        cls.leader = make_user(username='leader')
        cls.member = make_user(username='member')
        cls.client_user = make_user(User.Role.CLIENT, username='client1')
        cls.outsider = make_user(username='outsider')

        cls.team = make_team(leader=cls.leader, members=[cls.member, cls.client_user])
        cls.project = make_project(cls.leader, cls.team, name='Proyecto Visible')
        cls.hidden_project = make_project(cls.outsider, name='Proyecto Oculto')
        cls.task = make_task(
            cls.project, creator=cls.leader, assigned_user=cls.member, title='Tarea visible',
        )
        cls.hidden_task = make_task(cls.hidden_project, creator=cls.outsider, title='Tarea oculta')


class TempMediaMixin:

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()