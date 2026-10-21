from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import Notification
from tasks.models import Task

class Command(BaseCommand):
    help = 'Crea notificaciones para las tareas que vencen pronto o ya vencieron.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=1,
            help='Dias de anticipación para avisar (por defecto 1).',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        limit = today + timedelta(days=options['days'])
        day_start = timezone.make_aware(datetime.combine(today, time.min))

        tasks = (
            Task.objects.exclude(status=Task.Status.DONE)
            .filter(assigned_user__isnull=False, due_date__lte=limit)
            .select_related('assigned_user')
        )

        created = 0
        for task in tasks:
            already_sent = Notification.objects.filter(
                user=task.assigned_user, task=task,
                type=Notification.Type.DUE_DATE, created_at__gte=day_start,
            ).exists()
            
            if already_sent:
                continue

            days_left = (task.due_date - today).days
            
            if days_left < 0:
                state = 'Vencida'
            elif days_left == 0:
                state = 'Vence hoy'
            elif days_left == 1:
                state = 'Vence mañana'
            else:
                state = f'Vence en {days_left} días'

            Notification.objects.create(
                user=task.assigned_user,
                task=task,
                type=Notification.Type.DUE_DATE,
                message=f'{state}: "{task.title}"'[:255],
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f'{created} notificacion(es) creada(s).'))
