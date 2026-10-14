from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from notifications.models import Notification
from projects.models import Project
from tasks.models import Task, TimeLog


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        week_end = today + timedelta(days=7)

        my_tasks = Task.objects.filter(assigned_user=user)
        not_done = ~Q(status=Task.Status.DONE)

        # Una sola consulta que calcula las cuatro cifras
        context['stats'] = my_tasks.aggregate(
            todo=Count('id', filter=Q(status=Task.Status.TODO)),
            doing=Count('id', filter=Q(status=Task.Status.DOING)),
            due_soon=Count('id', filter=not_done & Q(due_date__range=(today, week_end))),
            overdue=Count('id', filter=not_done & Q(due_date__lt=today)),
        )

        context['month_hours'] = TimeLog.objects.filter(
            user=user, date__gte=today.replace(day=1),
        ).aggregate(total=Sum('hours'))['total'] or 0

        context['upcoming_tasks'] = (
            my_tasks.filter(not_done)
            .select_related('project')
            .prefetch_related('tags')
            .order_by(F('due_date').asc(nulls_last=True))[:5]
        )

        # Proyectos donde soy dueño, miembro del equipo o tengo tareas asignadas.
        # Se obtienen primero los ids para que los conteos de abajo
        # no se vean afectados por esos filtros.
        project_ids = Project.objects.filter(
            Q(owner=user) | Q(team__members=user) | Q(tasks__assigned_user=user)
        ).values('id')

        projects = list(
            Project.objects.filter(id__in=project_ids)
            .exclude(status__in=[Project.Status.COMPLETED, Project.Status.CANCELLED])
            .annotate(
                total=Count('tasks'),
                done=Count('tasks', filter=Q(tasks__status=Task.Status.DONE)),
            )
            .order_by('due_date')[:5]
        )
        for project in projects:
            project.progress = round(100 * project.done / project.total) if project.total else 0
        context['projects'] = projects

        context['notifications'] = (
            Notification.objects.filter(user=user).select_related('task')[:5]
        )
        context['unread_count'] = Notification.objects.filter(user=user, is_read=False).count()
        context['today'] = today
        return context