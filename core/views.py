from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from core.charts import build_donut

from notifications.models import Notification
from projects.models import Project
from tasks.models import Task, TimeLog

WEEKDAY_LABELS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        week_end = today + timedelta(days=7)

        my_tasks = Task.objects.filter(assigned_user=user)
        not_done = ~Q(status=Task.Status.DONE)

        # Una sola consulta que calcula todas las cifras
        stats = my_tasks.aggregate(
            todo=Count('id', filter=Q(status=Task.Status.TODO)),
            doing=Count('id', filter=Q(status=Task.Status.DOING)),
            done=Count('id', filter=Q(status=Task.Status.DONE)),
            due_soon=Count('id', filter=not_done & Q(due_date__range=(today, week_end))),
            overdue=Count('id', filter=not_done & Q(due_date__lt=today)),
        )
        context['stats'] = stats
        context['donut'] = build_donut(stats['todo'], stats['doing'], stats['done'])
        context['week'] = self.build_week(user, today)

        context['month_hours'] = TimeLog.objects.filter(
            user=user, date__gte=today.replace(day=1),
        ).aggregate(total=Sum('hours'))['total'] or 0

        context['upcoming_tasks'] = (
            my_tasks.filter(not_done)
            .select_related('project')
            .prefetch_related('tags')
            .order_by(F('due_date').asc(nulls_last=True))[:5]
        )

        context['projects'] = list(
            Project.objects.visible_to(user)
            .exclude(status__in=[Project.Status.COMPLETED, Project.Status.CANCELLED])
            .with_task_counts()
            .order_by('due_date')[:5]
        )

        context['notifications'] = (
            Notification.objects.filter(user=user).select_related('task')[:5]
        )
        context['unread_count'] = Notification.objects.filter(user=user, is_read=False).count()
        context['today'] = today
        return context


    @staticmethod
    def build_week(user, today):
        """Horas registradas por día en la semana actual (de lunes a domingo)."""
        start = today - timedelta(days=today.weekday())
        rows = (
            TimeLog.objects.filter(
                user=user,
                date__range=(start, start + timedelta(days=6)),
                task__in=Task.objects.visible_to(user),
            )
            .values('date')
            .annotate(total=Sum('hours'))
        )
        totals = {row['date']: row['total'] for row in rows}
        # La escala mínima es 8 h, para que un día corto no parezca una jornada completa
        scale = max(max(totals.values(), default=Decimal('0')), Decimal('8'))

        days = []
        for offset in range(7):
            day = start + timedelta(days=offset)
            total = totals.get(day, Decimal('0'))
            days.append({
                'label': WEEKDAY_LABELS[offset],
                'total': total,
                'percent': max(12, round(100 * total / scale)) if total else 0,
                'is_today': day == today,
            })
        return {'days': days, 'total': sum(totals.values(), Decimal('0'))}