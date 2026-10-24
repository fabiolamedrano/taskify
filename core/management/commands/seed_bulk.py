import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from projects.models import Project
from tasks.models import Attachment, Comment, Subtask, Tag, Task, TimeLog
from teams.models import Team, TeamMember

User = get_user_model()

PASSWORD = 'taskify123'  # solo para desarrollo
PREFIX = 'demo_'

FIRST_NAMES = [
    'Sofía', 'Mateo', 'Valentina', 'Santiago', 'Camila', 'Diego', 'Lucía', 'Andrés', 'Paula',
    'Javier', 'Daniela', 'Sebastián', 'Mariana', 'Emilio', 'Renata', 'Gabriel', 'Ximena',
]
LAST_NAMES = [
    'García', 'Hernández', 'López', 'Martínez', 'Rodríguez', 'Pérez', 'Sánchez', 'Ramírez',
    'Flores', 'Torres', 'Díaz', 'Vargas', 'Castillo', 'Morales', 'Ortega', 'Mendoza',
]
TEAM_NAMES = [
    'Diseño de producto', 'Desarrollo web', 'Móvil', 'Calidad (QA)',
    'Marketing digital', 'Datos y analítica', 'Soporte al cliente', 'Infraestructura',
]
TEAM_ROLES = ['Diseño', 'Frontend', 'Backend', 'QA', 'Producto', 'Análisis', 'Soporte']
PROJECT_NAMES = [
    'Rediseño del portal', 'App móvil de reservas', 'Migración a la nube', 'Campaña de lanzamiento',
    'Panel de analítica', 'Integración de pagos', 'Sitio de documentación', 'Programa de fidelización',
    'Automatización de reportes', 'Tienda en línea', 'Intranet corporativa', 'Asistente de soporte',
]
ACTIONS = [
    'Definir requisitos de {x}', 'Diseñar la maqueta de {x}', 'Implementar {x}',
    'Revisar {x} con el cliente', 'Probar {x} en móvil', 'Documentar {x}', 'Optimizar {x}',
    'Corregir errores de {x}', 'Preparar la demo de {x}', 'Migrar los datos de {x}',
]
AREAS = [
    'inicio de sesión', 'panel principal', 'buscador', 'carrito', 'notificaciones',
    'perfil de usuario', 'reportes', 'facturación', 'calendario', 'formulario de contacto',
    'galería', 'API de pagos', 'permisos por rol', 'correo de bienvenida', 'página de precios',
]
SUBTASK_TITLES = [
    'Revisar los requisitos', 'Preparar datos de prueba', 'Escribir la primera versión',
    'Pedir retroalimentación', 'Corregir observaciones', 'Validar en móvil', 'Actualizar la documentación',
]
COMMENTS = [
    'Ya tengo un avance, lo subo hoy.', '¿Podemos revisarlo en la reunión de mañana?',
    'Falta confirmar este punto con el cliente.', 'Quedó listo, pendiente de revisión.',
    'Encontré un detalle en la versión móvil.', 'Lo muevo a la próxima semana, hay otra prioridad.',
    'Buen trabajo, solo ajusta los textos.',
]
LOG_NOTES = ['Avance de la tarea', 'Reunión con el equipo', 'Revisión y ajustes', 'Pruebas', 'Documentación']
TAGS = {
    'Bug': '#D92D20', 'Urgente': '#F59E0B', 'Diseño': '#6366F1',
    'Frontend': '#0EA5E9', 'Finanzas': '#2A9D8F',
}
# Probabilidades de (por hacer, en curso, hecho) según el estado del proyecto
STATUS_WEIGHTS = {
    Project.Status.ACTIVE: (35, 25, 40),
    Project.Status.PAUSED: (45, 20, 35),
    Project.Status.COMPLETED: (3, 2, 95),
}


class Command(BaseCommand):
    help = 'Genera muchos datos de demostración: usuarios, equipos, proyectos y tareas.'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=14, help='Usuarios demo con rol miembro (mínimo 4).')
        parser.add_argument('--teams', type=int, default=5)
        parser.add_argument('--projects', type=int, default=10)
        parser.add_argument('--tasks', type=int, default=18, help='Tareas por proyecto (aproximado).')
        parser.add_argument('--seed', type=int, default=7, help='La misma semilla genera siempre los mismos datos.')
        parser.add_argument('--reset', action='store_true', help='Borra los datos demo anteriores y los regenera.')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['users'] < 4 or min(options['teams'], options['projects'], options['tasks']) < 1:
            raise CommandError('Usa al menos 4 usuarios, 1 equipo, 1 proyecto y 1 tarea por proyecto.')
        if options['reset']:
            self.reset()
        elif User.objects.filter(username__startswith=PREFIX).exists():
            raise CommandError('Ya hay datos de demostración. Usa --reset para regenerarlos.')

        rng = random.Random(options['seed'])
        today = timezone.localdate()

        demo_members, demo_clients = self.create_users(rng, options['users'])
        existing = list(
            User.objects.filter(is_active=True)
            .exclude(username__startswith=PREFIX).exclude(role=User.Role.CLIENT)
        )
        teams = self.create_teams(rng, options['teams'], demo_members, demo_clients, existing)
        tags = self.ensure_tags()

        for index in range(options['projects']):
            team, members = teams[index % len(teams)]
            project = self.create_project(rng, index, team, today)
            for _ in range(rng.randint(max(5, options['tasks'] - 6), options['tasks'] + 6)):
                self.create_task(rng, project, team, members, tags, today)

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {Team.objects.filter(leader__username__startswith=PREFIX).count()} equipos, '
            f'{Project.objects.filter(owner__username__startswith=PREFIX).count()} proyectos y '
            f'{Task.objects.filter(creator__username__startswith=PREFIX).count()} tareas.'
        ))
        self.stdout.write(f'Inicia sesión con demo_01 … demo_{options["users"]:02d} o demo_c1 (cliente). Contraseña: {PASSWORD}')

    def reset(self):
        # El orden importa: proyectos y tareas protegen a sus usuarios (PROTECT)
        Project.objects.filter(owner__username__startswith=PREFIX).delete()
        Team.objects.filter(leader__username__startswith=PREFIX).delete()
        User.objects.filter(username__startswith=PREFIX).delete()
        self.stdout.write('Datos de demostración anteriores borrados.')

    def create_users(self, rng, count):
        hashed = make_password(PASSWORD)  # se calcula una vez y se reutiliza: es lento
        members = [
            User.objects.create(
                username=f'{PREFIX}{number:02d}', email=f'{PREFIX}{number:02d}@taskify.test',
                first_name=rng.choice(FIRST_NAMES), last_name=rng.choice(LAST_NAMES),
                role=User.Role.MEMBER, password=hashed,
            )
            for number in range(1, count + 1)
        ]
        clients = [
            User.objects.create(
                username=f'{PREFIX}c{number}', email=f'{PREFIX}c{number}@taskify.test',
                first_name=rng.choice(FIRST_NAMES), last_name=rng.choice(LAST_NAMES),
                role=User.Role.CLIENT, password=hashed,
            )
            for number in (1, 2)
        ]
        return members, clients

    def create_teams(self, rng, count, demo_members, demo_clients, existing):
        # Los usuarios que ya tenías (ana, luis...) también entran a los equipos
        pool = demo_members + existing
        names = TEAM_NAMES[:]
        rng.shuffle(names)
        teams = []
        for index in range(count):
            name = names[index] if index < len(names) else f'Equipo {index + 1}'
            leader = rng.choice(demo_members)  # siempre demo, para poder borrarlo con --reset
            others = [user for user in pool if user.pk != leader.pk]
            members = [leader, *rng.sample(others, min(len(others), rng.randint(3, 7)))]
            team = Team.objects.create(
                name=name, description=f'Equipo de demostración: {name.lower()}.', leader=leader,
            )
            TeamMember.objects.bulk_create([
                TeamMember(
                    team=team, user=user,
                    role_in_team='Líder' if user == leader else rng.choice(TEAM_ROLES),
                )
                for user in members
            ])
            if rng.random() < 0.5:  # algunos equipos tienen un cliente (solo lectura)
                TeamMember.objects.create(team=team, user=rng.choice(demo_clients), role_in_team='Cliente')
            teams.append((team, members))
        return teams

    def ensure_tags(self):
        for name, color in TAGS.items():
            Tag.objects.get_or_create(name=name, defaults={'color': color})
        return list(Tag.objects.all())

    def create_project(self, rng, index, team, today):
        status = rng.choices(
            [Project.Status.ACTIVE, Project.Status.PAUSED, Project.Status.COMPLETED],
            weights=[7, 1, 2],
        )[0]
        if status == Project.Status.COMPLETED:
            due = today - timedelta(days=rng.randint(1, 20))
            start = due - timedelta(days=rng.randint(60, 120))
        else:
            start = today - timedelta(days=rng.randint(15, 100))
            due = start + timedelta(days=rng.randint(45, 160))
        name = PROJECT_NAMES[index % len(PROJECT_NAMES)]
        if index >= len(PROJECT_NAMES):
            name = f'{name} {index // len(PROJECT_NAMES) + 1}'
        return Project.objects.create(
            name=name, description=f'Proyecto de demostración: {name.lower()}.',
            objective='Entregar una primera versión funcional y medir su uso.',
            budget=Decimal(rng.randrange(5, 81)) * 1000,
            start_date=start, due_date=due, status=status,
            owner=team.leader, team=team,
        )

    def create_task(self, rng, project, team, members, tags, today):
        status = rng.choices(
            [Task.Status.TODO, Task.Status.DOING, Task.Status.DONE],
            weights=STATUS_WEIGHTS[project.status],
        )[0]
        if status == Task.Status.DONE:
            due = today - timedelta(days=rng.randint(1, 35))
        else:
            due = today + timedelta(days=rng.randint(-6, 35))  # algunas quedan vencidas
        assignee = rng.choice(members) if rng.random() < 0.9 else None

        task = Task.objects.create(
            project=project, creator=project.owner,
            title=rng.choice(ACTIONS).format(x=rng.choice(AREAS)),
            description=f'Tarea de demostración del proyecto «{project.name}».',
            priority=rng.choices(
                [Task.Priority.HIGH, Task.Priority.MEDIUM, Task.Priority.LOW], weights=[2, 5, 3],
            )[0],
            status=status,
            start_date=due - timedelta(days=rng.randint(3, 14)),
            due_date=due,
            estimated_hours=Decimal(rng.randrange(8, 161)) / 4,
            assigned_user=assignee,
            assigned_team=team if assignee is None and rng.random() < 0.5 else None,
        )
        task.tags.set(rng.sample(tags, rng.randint(0, 2)))

        for order in range(rng.choice([0, 0, 2, 3, 4, 5])):
            done = status == Task.Status.DONE or (status == Task.Status.DOING and rng.random() < 0.4)
            Subtask.objects.create(
                task=task, title=rng.choice(SUBTASK_TITLES), is_completed=done, order=order,
            )

        if status != Task.Status.TODO:
            for _ in range(rng.randint(0, 3)):
                TimeLog.objects.create(
                    task=task, user=assignee or rng.choice(members),
                    date=today - timedelta(days=rng.randint(0, 27)),
                    hours=Decimal(rng.randrange(2, 33)) / 4,  # de 0,5 a 8 horas
                    description=rng.choice(LOG_NOTES),
                )

        first = None
        for _ in range(rng.choice([0, 0, 1, 2, 3])):
            comment = Comment.objects.create(
                task=task, author=rng.choice(members), content=rng.choice(COMMENTS),
                parent=first if first and rng.random() < 0.4 else None,
            )
            first = first or comment

        if rng.random() < 0.2:
            Attachment.objects.create(
                task=task, uploaded_by=project.owner, file_name='Documento de referencia',
                type=Attachment.Type.LINK, url=f'https://example.com/docs/{task.pk}',
            )

        if assignee and rng.random() < 0.35:
            Notification.objects.create(
                user=assignee, task=task, type=Notification.Type.ASSIGNMENT,
                message=f'Se te asignó "{task.title}"'[:255],
                is_read=status == Task.Status.DONE or rng.random() < 0.4,
            )
        if assignee and status != Task.Status.DONE and due < today and rng.random() < 0.6:
            Notification.objects.create(
                user=assignee, task=task, type=Notification.Type.DUE_DATE,
                message=f'Vencida: "{task.title}"'[:255],
            )

        if status == Task.Status.DONE:
            # Fechas de cierre variadas, para que la columna «Hecho» tenga un orden real
            Task.objects.filter(pk=task.pk).update(
                updated_at=timezone.now() - timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 23)),
            )
        return task