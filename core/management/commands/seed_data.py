from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from projects.models import Project
from tasks.models import Comment, Subtask, Tag, Task, TimeLog
from teams.models import Team, TeamMember

User = get_user_model()

PASSWORD = 'taskify123'  # solo para desarrollo

USERS = [
    ('ana', 'Ana', 'Torres', User.Role.ADMIN),
    ('luis', 'Luis', 'Pérez', User.Role.MEMBER),
    ('maria', 'María', 'Gómez', User.Role.MEMBER),
    ('carlos', 'Carlos', 'Ruiz', User.Role.MEMBER),
    ('cliente', 'Elena', 'Vargas', User.Role.CLIENT),
]

TAGS = {
    'Bug': '#D92D20',
    'Urgente': '#F59E0B',
    'Diseño': '#6366F1',
    'Frontend': '#0EA5E9',
    'Finanzas': '#2A9D8F',
}

# (clave, nombre, dueño, equipo, presupuesto, inicio, fin, estado)
# Las fechas son días relativos a hoy.
PROJECTS = [
    ('web', 'Sitio web corporativo', 'ana', 'dev', 15000, -30, 20, Project.Status.ACTIVE),
    ('app', 'App de reservas', 'luis', 'dev', 28000, -10, 60, Project.Status.ACTIVE),
    ('marketing', 'Campaña de marketing', 'ana', 'design', 9000, -45, 15, Project.Status.PAUSED),
]

TASKS = [
    {
        'project': 'web',
        'title': 'Diseñar pantalla de login',
        'status': Task.Status.DOING,
        'priority': Task.Priority.HIGH,
        'due': 2,
        'hours': 8,
        'assignee': 'maria',
        'tags': ['Diseño', 'Urgente'],
        'subtasks': [
            ('Definir campos del formulario', True),
            ('Diseñar versión móvil', False),
            ('Revisar con el cliente', False),
        ],
        'logs': [('maria', 3, 2, 'Boceto inicial'), ('maria', 2, 1.5, 'Versión de escritorio')],
        'comments': [
            ('luis', '¿Podemos agregar inicio de sesión con Google?'),
            ('maria', 'Buena idea, lo incluyo en el prototipo.'),
        ],
    },
    {
        'project': 'web',
        'title': 'Maquetar dashboard',
        'status': Task.Status.DOING,
        'priority': Task.Priority.HIGH,
        'due': 5,
        'hours': 12,
        'assignee': 'carlos',
        'tags': ['Frontend'],
        'subtasks': [
            ('Estructura HTML', True),
            ('Estilos con Tailwind', True),
            ('Versión móvil', False),
        ],
        'logs': [('carlos', 1, 4, 'Estructura y estilos base')],
    },
    {
        'project': 'web',
        'title': 'Corregir error en formulario de contacto',
        'status': Task.Status.TODO,
        'priority': Task.Priority.LOW,
        'due': 8,
        'hours': 2,
        'assignee': 'luis',
        'tags': ['Bug'],
    },
    {
        'project': 'web',
        'title': 'Definir presupuesto de hosting',
        'status': Task.Status.TODO,
        'priority': Task.Priority.MEDIUM,
        'due': 1,
        'hours': 3,
        'assignee': 'ana',
        'tags': ['Finanzas'],
        'subtasks': [('Comparar proveedores', False), ('Pedir cotizaciones', False)],
    },
    {
        'project': 'web',
        'title': 'Wireframes de escritorio',
        'status': Task.Status.DONE,
        'priority': Task.Priority.MEDIUM,
        'due': -5,
        'hours': 6,
        'assignee': 'maria',
        'tags': ['Diseño'],
        'subtasks': [('Tablero de tareas', True), ('Detalle de tarea', True)],
        'logs': [('maria', 8, 3, 'Tablero'), ('maria', 7, 2.5, 'Detalle de tarea')],
    },
    {
        'project': 'web',
        'title': 'Reunión de arranque con el cliente',
        'status': Task.Status.DONE,
        'priority': Task.Priority.HIGH,
        'due': -20,
        'hours': 2,
        'assignee': 'ana',
        'tags': ['Urgente'],
        'logs': [('ana', 21, 2, 'Reunión y acta')],
    },
    {
        'project': 'app',
        'title': 'Modelar base de datos de reservas',
        'status': Task.Status.DOING,
        'priority': Task.Priority.HIGH,
        'due': 0,
        'hours': 10,
        'assignee': 'luis',
        'tags': [],
        'subtasks': [('Diagrama entidad-relación', True), ('Escribir modelos', False)],
        'logs': [('luis', 1, 3, 'Diagrama ER')],
    },
    {
        'project': 'app',
        'title': 'Pantalla de búsqueda de disponibilidad',
        'status': Task.Status.TODO,
        'priority': Task.Priority.MEDIUM,
        'due': 14,
        'hours': 16,
        'assignee': 'maria',
        'tags': ['Frontend', 'Diseño'],
    },
    {
        'project': 'app',
        'title': 'Integrar pasarela de pagos',
        'status': Task.Status.TODO,
        'priority': Task.Priority.HIGH,
        'due': -2,
        'hours': 20,
        'assignee': 'carlos',
        'tags': ['Finanzas', 'Urgente'],
        'comments': [('luis', 'Esta tarea está atrasada, ¿necesitas ayuda?')],
    },
    {
        'project': 'app',
        'title': 'Pruebas de carga',
        'status': Task.Status.TODO,
        'priority': Task.Priority.LOW,
        'due': 40,
        'hours': 8,
        'team': 'dev',
        'tags': [],
    },
    {
        'project': 'marketing',
        'title': 'Calendario de contenido',
        'status': Task.Status.DOING,
        'priority': Task.Priority.MEDIUM,
        'due': 6,
        'hours': 5,
        'assignee': 'ana',
        'tags': ['Diseño'],
        'subtasks': [('Definir temas', True), ('Programar publicaciones', False)],
    },
    {
        'project': 'marketing',
        'title': 'Análisis de la competencia',
        'status': Task.Status.DONE,
        'priority': Task.Priority.MEDIUM,
        'due': -8,
        'hours': 6,
        'assignee': 'ana',
        'tags': [],
        'logs': [('ana', 10, 5, 'Investigación y resumen')],
    },
]


class Command(BaseCommand):
    help = 'Carga datos de ejemplo para desarrollo y demostración.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Borra los datos de ejemplo (menos los superusuarios) antes de cargar.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self.reset()

        users = self.create_users()
        teams = self.create_teams(users)
        projects = self.create_projects(users, teams)
        tags = self.create_tags()
        created = self.create_tasks(users, teams, projects, tags)

        self.stdout.write(self.style.SUCCESS(f'Listo: {created} tareas nuevas.'))
        self.stdout.write(f'Usuarios de ejemplo: ana, luis, maria, carlos, cliente (contraseña: {PASSWORD})')

    def reset(self):
        # El orden importa: Task y Project usan PROTECT hacia el usuario
        Notification.objects.all().delete()
        Task.objects.all().delete()
        Project.objects.all().delete()
        Team.objects.all().delete()
        Tag.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('Datos anteriores borrados.')

    def create_users(self):
        users = {}
        for username, first, last, role in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@taskify.test',
                    'role': role,
                },
            )
            if created:
                user.set_password(PASSWORD)  # guarda el hash, no el texto
                user.save()
            users[username] = user
        return users

    def create_teams(self, users):
        design, _ = Team.objects.get_or_create(
            name='Diseño UX',
            defaults={'description': 'Interfaces y experiencia de usuario', 'leader': users['ana']},
        )
        dev, _ = Team.objects.get_or_create(
            name='Desarrollo',
            defaults={'description': 'Backend y frontend', 'leader': users['luis']},
        )
        members = [
            (design, 'ana', 'Líder'),
            (design, 'maria', 'Diseñadora'),
            (dev, 'luis', 'Líder'),
            (dev, 'carlos', 'Backend'),
            (dev, 'maria', 'Frontend'),
        ]
        for team, username, role in members:
            TeamMember.objects.get_or_create(
                team=team, user=users[username], defaults={'role_in_team': role},
            )
        return {'design': design, 'dev': dev}

    def create_projects(self, users, teams):
        today = timezone.localdate()
        projects = {}
        for key, name, owner, team, budget, start, end, status in PROJECTS:
            project, _ = Project.objects.get_or_create(
                name=name,
                defaults={
                    'description': f'Proyecto de ejemplo: {name}',
                    'owner': users[owner],
                    'team': teams[team],
                    'budget': budget,
                    'start_date': today + timedelta(days=start),
                    'due_date': today + timedelta(days=end),
                    'status': status,
                },
            )
            projects[key] = project
        return projects

    def create_tags(self):
        tags = {}
        for name, color in TAGS.items():
            tags[name], _ = Tag.objects.get_or_create(name=name, defaults={'color': color})
        return tags

    def create_tasks(self, users, teams, projects, tags):
        today = timezone.localdate()
        count = 0

        for item in TASKS:
            project = projects[item['project']]
            due = today + timedelta(days=item['due'])
            assignee = users.get(item.get('assignee'))

            task, created = Task.objects.get_or_create(
                project=project,
                title=item['title'],
                defaults={
                    'description': item.get('description', ''),
                    'status': item['status'],
                    'priority': item['priority'],
                    'start_date': due - timedelta(days=7),
                    'due_date': due,
                    'estimated_hours': item['hours'],
                    'creator': project.owner,
                    'assigned_user': assignee,
                    'assigned_team': teams[item['team']] if item.get('team') else None,
                },
            )
            if not created:
                continue  # ya existía: no duplicamos sus datos
            count += 1

            task.tags.set([tags[name] for name in item['tags']])

            for order, (title, done) in enumerate(item.get('subtasks', [])):
                Subtask.objects.create(task=task, title=title, is_completed=done, order=order)

            parent = None
            for username, text in item.get('comments', []):
                comment = Comment.objects.create(
                    task=task, author=users[username], content=text, parent=parent,
                )
                parent = parent or comment  # los siguientes responden al primero

            for username, days_ago, hours, description in item.get('logs', []):
                TimeLog.objects.create(
                    task=task,
                    user=users[username],
                    date=today - timedelta(days=days_ago),
                    hours=Decimal(str(hours)),
                    description=description,
                )

            if assignee:
                done = task.status == Task.Status.DONE
                Notification.objects.create(
                    user=assignee, task=task, type=Notification.Type.ASSIGNMENT,
                    message=f'Se te asignó "{task.title}"', is_read=done,
                )
                if not done and item['due'] <= 2:
                    state = 'Vencida' if item['due'] < 0 else 'Vence pronto'
                    Notification.objects.create(
                        user=assignee, task=task, type=Notification.Type.DUE_DATE,
                        message=f'{state}: "{task.title}"',
                    )

        return count