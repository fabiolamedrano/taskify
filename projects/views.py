from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Sum
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.charts import build_donut
from core.mixins import QueryStringMixin, filter_options
from core.permissions import NotClientMixin, OwnerOrAdminMixin
from core.formatting import plain, plural
from tasks.models import Comment, Task, TimeLog

from .forms import ProjectForm
from .models import Project


class ProjectListView(LoginRequiredMixin, QueryStringMixin, ListView):
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 12

    def get_search(self):
        return self.request.GET.get('q', '').strip()

    def get_status(self):
        status = self.request.GET.get('status', '')
        return status if status in Project.Status.values else ''

    def get_base_queryset(self):
        queryset = Project.objects.visible_to(self.request.user)
        search = self.get_search()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def get_queryset(self):
        queryset = self.get_base_queryset().select_related('owner', 'team').with_task_counts()
        status = self.get_status()
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-created_at', '-id')

    def url_without(self, param):
        params = self.request.GET.copy()
        params.pop(param, None)
        params.pop('page', None)
        query = params.urlencode()
        return f'?{query}' if query else self.request.path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = dict(
            self.get_base_queryset().order_by().values_list('status').annotate(n=Count('pk'))
        )
        status = self.get_status()
        context.update(
            status_options=filter_options(
                self.request, 'status', Project.Status.choices, status,
                all_label='Todos', counts=counts,
            ),
            current_status=status,
            q=self.get_search(),
            clear_search_url=self.url_without('q'),
            today=timezone.localdate(),
        )
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'
    WEEKS = 6

    def get_queryset(self):
        # Si el usuario no puede ver el proyecto, Django responde 404
        return (
            Project.objects.visible_to(self.request.user)
            .select_related('owner', 'team')
            .with_task_counts()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        user = self.request.user
        today = timezone.localdate()

        # Una sola consulta de tareas; el resto se calcula en Python
        all_tasks = list(
            project.tasks.select_related('assigned_user', 'assigned_team')
            .prefetch_related('tags')
            .order_by(F('due_date').asc(nulls_last=True), 'id')
        )
        counts = Counter(task.status for task in all_tasks)
        done, doing, todo = counts['done'], counts['doing'], counts['todo']
        open_count = len(all_tasks) - done
        overdue_count = sum(1 for task in all_tasks if task.is_overdue)

        status = self.request.GET.get('status', '')
        status = status if status in Task.Status.values else ''
        shown = [task for task in all_tasks if task.status == status] if status else all_tasks

        logged = TimeLog.objects.filter(task__project=project).aggregate(
            total=Sum('hours'))['total'] or Decimal('0')
        estimated = project.tasks.aggregate(total=Sum('estimated_hours'))['total'] or Decimal('0')

        open_by_user = Counter(
            task.assigned_user_id for task in all_tasks if task.status != Task.Status.DONE
        )
        members = list(project.team.members.order_by('first_name', 'username')) if project.team else []
        for member in members:
            member.open_tasks = open_by_user[member.pk]

        context.update(
            cards=[
                {
                    'label': 'Progreso', 'value': project.progress, 'unit': '%', 'dark': True,
                    'caption': f'{done} de {plural(len(all_tasks), "tarea")}',
                    'href': reverse('tasks:board', args=[project.pk]),
                },
                {
                    'label': 'Tareas abiertas', 'value': open_count, 'unit': '', 'href': '#tasks',
                    'caption': plural(overdue_count, 'vencida') if overdue_count else 'Ninguna vencida',
                },
                {
                    'label': 'Horas registradas', 'value': plain(logged), 'unit': ' h', 'href': '#hours',
                    'caption': f'de {plain(estimated)} h estimadas',
                },
                {**self.deadline_card(project, today), 'label': 'Fecha límite', 'href': '#details'},
            ],
            tasks=shown,
            task_filter=filter_options(
                self.request, 'status', Task.Status.choices, status,
                all_label='Todas', counts=counts, fragment='tasks',
            ),
            my_tasks=[
                task for task in all_tasks
                if task.assigned_user_id == user.pk and task.status != Task.Status.DONE
            ][:6],
            status_counts={'todo': todo, 'doing': doing, 'done': done},
            donut=build_donut(todo, doing, done),
            weekly=self.weekly_hours(project, today),
            workload=self.workload(all_tasks),
            members=members,
            comments=Comment.objects.filter(task__project=project)
            .select_related('author', 'task').order_by('-created_at', '-id')[:4],
            today=today,
        )
        return context

    @staticmethod
    def deadline_card(project, today):
        if not project.due_date:
            return {'value': '—', 'unit': '', 'caption': 'Sin fecha límite', 'alert': False}
        days = (project.due_date - today).days
        when = date_format(project.due_date, 'j M Y')
        unit = ' día' if abs(days) == 1 else ' días'
        if days < 0:
            return {
                'value': -days, 'unit': unit, 'caption': f'Venció el {when}',
                'alert': project.status == Project.Status.ACTIVE,
            }
        return {'value': days, 'unit': unit, 'caption': f'Vence el {when}', 'alert': False}

    @classmethod
    def weekly_hours(cls, project, today):
        """Horas del proyecto en las últimas semanas (de lunes a domingo)."""
        this_week = today - timedelta(days=today.weekday())
        first = this_week - timedelta(weeks=cls.WEEKS - 1)
        rows = (
            TimeLog.objects.filter(task__project=project, date__gte=first)
            .order_by().values('date').annotate(total=Sum('hours'))
        )
        totals = defaultdict(Decimal)
        for row in rows:
            totals[row['date'] - timedelta(days=row['date'].weekday())] += row['total']
        scale = max(max(totals.values(), default=Decimal('0')), Decimal('1'))

        bars = []
        for index in range(cls.WEEKS):
            start = first + timedelta(weeks=index)
            total = totals.get(start, Decimal('0'))
            bars.append({
                'start': start,
                'total': total,
                'percent': max(12, round(100 * total / scale)) if total else 0,
                'is_current': start == this_week,
            })
        return bars

    @staticmethod
    def workload(tasks):
        """Tareas totales y completadas por persona."""
        rows = {}
        for task in tasks:
            user = task.assigned_user
            key = user.pk if user else None
            name = (user.get_full_name() or user.username) if user else 'Sin responsable'
            row = rows.setdefault(key, {'name': name, 'total': 0, 'done': 0})
            row['total'] += 1
            row['done'] += task.status == Task.Status.DONE
        result = sorted(rows.values(), key=lambda row: (-row['total'], row['name']))
        for row in result:
            row['percent'] = round(100 * row['done'] / row['total'])
        return result

class ProjectFormMixin:
    form_class = ProjectForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class ProjectCreateView(NotClientMixin, ProjectFormMixin, CreateView):
    model = Project

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Proyecto creado.')
        return super().form_valid(form)


class ProjectUpdateView(NotClientMixin, OwnerOrAdminMixin, ProjectFormMixin, UpdateView):
    owner_field = 'owner_id'

    def get_queryset(self):
        return Project.objects.visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Proyecto actualizado.')
        return super().form_valid(form)


class ProjectDeleteView(NotClientMixin, OwnerOrAdminMixin, DeleteView):
    owner_field = 'owner_id'
    success_url = reverse_lazy('projects:list')

    def get_queryset(self):
        return Project.objects.visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['task_count'] = self.object.tasks.count()
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Proyecto "{self.object.name}" eliminado.')
        return super().form_valid(form)