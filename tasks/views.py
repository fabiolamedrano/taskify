from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from operator import attrgetter

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from core.permissions import NotClientMixin, OwnerOrAdminMixin
from core.mixins import filter_options
from notifications.models import Notification
from projects.models import Project

from .forms import AttachmentForm, CommentForm, QuickTimeLogForm, SubtaskForm, TaskForm, TimeLogForm
from .models import Attachment, Comment, Subtask, Task, TimeLog
from .services import notify_assignment

class BoardView(LoginRequiredMixin, DetailView):
    template_name = 'tasks/board.html'
    context_object_name = 'project'
    pk_url_kwarg = 'project_pk'
    DONE_LIMIT = 12  # «Hecho» muestra solo las más recientes

    def get_queryset(self):
        return (
            Project.objects.visible_to(self.request.user)
            .select_related('owner', 'team')
            .with_task_counts()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        params = self.request.GET

        assigned = params.get('assigned', '')
        assigned = assigned if assigned in ('mine', 'none') else ''
        priority = params.get('priority', '')
        priority = priority if priority in Task.Priority.values else ''

        tasks = self.object.tasks.all()
        if assigned == 'mine':
            tasks = tasks.filter(assigned_user=user)
        elif assigned == 'none':
            tasks = tasks.filter(assigned_user__isnull=True)
        if priority:
            tasks = tasks.filter(priority=priority)

        tasks = (
            tasks.select_related('assigned_user', 'assigned_team')
            .prefetch_related('tags')
            .annotate(
                subtask_total=Count('subtasks', distinct=True),
                subtask_done=Count('subtasks', filter=Q(subtasks__is_completed=True), distinct=True),
                comment_total=Count('comments', distinct=True),
            )
            .order_by(F('due_date').asc(nulls_last=True), 'id')
        )

        # Una sola consulta; las tareas se reparten por estado en Python
        by_status = {value: [] for value, _ in Task.Status.choices}
        for task in tasks:
            task.subtask_percent = (
                round(100 * task.subtask_done / task.subtask_total) if task.subtask_total else 0
            )
            by_status[task.status].append(task)

        done_rows = sorted(by_status['done'], key=attrgetter('updated_at'), reverse=True)
        by_status['done'] = done_rows[:self.DONE_LIMIT]

        context.update(
            columns=[(value, label, by_status[value]) for value, label in Task.Status.choices],
            done_hidden=len(done_rows) - len(by_status['done']),
            statuses=Task.Status.choices,
            assigned_options=filter_options(
                self.request, 'assigned', [('mine', 'Mías'), ('none', 'Sin asignar')],
                assigned, all_label='Todas',
            ),
            priority_options=filter_options(
                self.request, 'priority', Task.Priority.choices, priority, all_label='Todas',
            ),
            has_filters=bool(assigned or priority),
            can_move=not user.is_client,
            today=timezone.localdate(),
        )
        return context


class TaskDetailView(LoginRequiredMixin, DetailView):
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task'

    def get_queryset(self):
        return (
            Task.objects.visible_to(self.request.user)
            .select_related('project', 'creator', 'assigned_user', 'assigned_team')
            .prefetch_related('tags')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object
        today = timezone.localdate()

        subtasks = list(task.subtasks.all())
        done = sum(1 for subtask in subtasks if subtask.is_completed)

        context.update(
            subtasks=subtasks,
            subtasks_done=done,
            subtasks_progress=round(100 * done / len(subtasks)) if subtasks else 0,
            comments=task.comments.select_related('author'),
            attachments=task.attachments.select_related('uploaded_by'),
            time_logs=task.time_logs.select_related('user'),
            logged_hours=task.time_logs.aggregate(total=Sum('hours'))['total'] or 0,
            subtask_form=SubtaskForm(),
            comment_form=CommentForm(),
            time_form=TimeLogForm(initial={'date': today}),
            attachment_form=AttachmentForm(),
            can_edit=not self.request.user.is_client,
            today=today,
        )
        return context


class TaskActionView(LoginRequiredMixin, View):
    http_method_names = ['post']
    form_class = None
    anchor = ''
    success_message = ''

    def post(self, request, pk):
        if request.user.is_client:
            raise PermissionDenied
        task = get_object_or_404(Task.objects.visible_to(request.user), pk=pk)

        form = self.form_class(request.POST, request.FILES)
        if form.is_valid():
            self.save(form, task)
            messages.success(request, self.success_message)
        else:
            errors = [error for field_errors in form.errors.values() for error in field_errors]
            messages.error(request, ' '.join(errors))
        return redirect(f"{reverse('tasks:detail', args=[task.pk])}#{self.anchor}")

    def save(self, form, task):
        raise NotImplementedError


class SubtaskCreateView(TaskActionView):
    form_class = SubtaskForm
    anchor = 'subtasks'
    success_message = 'Subtarea agregada.'

    def save(self, form, task):
        subtask = form.save(commit=False)
        subtask.task = task
        last = task.subtasks.aggregate(last=Max('order'))['last']
        subtask.order = 0 if last is None else last + 1
        subtask.save()


class SubtaskToggleView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        if request.user.is_client:
            raise PermissionDenied
        visible_tasks = Task.objects.visible_to(request.user)
        subtask = get_object_or_404(Subtask.objects.filter(task__in=visible_tasks), pk=pk)
        subtask.is_completed = not subtask.is_completed
        subtask.save(update_fields=['is_completed'])
        return redirect(f"{reverse('tasks:detail', args=[subtask.task_id])}#subtasks")


class CommentCreateView(TaskActionView):
    form_class = CommentForm
    anchor = 'comments'
    success_message = 'Comentario publicado.'

    def save(self, form, task):
        comment = form.save(commit=False)
        comment.task = task
        comment.author = self.request.user
        comment.save()

        recipient = task.assigned_user
        if recipient and recipient != self.request.user:
            author = self.request.user.get_full_name() or self.request.user.username
            Notification.objects.create(
                user=recipient,
                task=task,
                type=Notification.Type.COMMENT,
                message=f'{author} comentó en "{task.title}"'[:255],
            )


class TimeLogCreateView(TaskActionView):
    form_class = TimeLogForm
    anchor = 'time'
    success_message = 'Tiempo registrado.'

    def save(self, form, task):
        log = form.save(commit=False)
        log.task = task
        log.user = self.request.user
        log.save()


class AttachmentCreateView(TaskActionView):
    form_class = AttachmentForm
    anchor = 'attachments'
    success_message = 'Adjunto agregado.'

    def save(self, form, task):
        attachment = form.save(commit=False)
        attachment.task = task
        attachment.uploaded_by = self.request.user
        attachment.save()

class TaskFormMixin:
    form_class = TaskForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, project=self.project)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context


class TaskCreateView(NotClientMixin, TaskFormMixin, CreateView):
    model = Task

    @cached_property
    def project(self):
        return get_object_or_404(
            Project.objects.visible_to(self.request.user), pk=self.kwargs['project_pk'],
        )

    def get_initial(self):
        initial = super().get_initial()
        status = self.request.GET.get('status')
        if status in Task.Status.values:
            initial['status'] = status
        return initial

    def form_valid(self, form):
        form.instance.project = self.project
        form.instance.creator = self.request.user
        response = super().form_valid(form)
        notify_assignment(self.object, self.request.user)
        messages.success(self.request, 'Tarea creada.')
        return response


class TaskUpdateView(NotClientMixin, TaskFormMixin, UpdateView):
    def get_queryset(self):
        return Task.objects.visible_to(self.request.user).select_related('project')

    @property
    def project(self):
        return self.object.project

    def form_valid(self, form):
        response = super().form_valid(form)
        if 'assigned_user' in form.changed_data:
            notify_assignment(self.object, self.request.user)
        messages.success(self.request, 'Tarea actualizada.')
        return response


class TaskDeleteView(NotClientMixin, OwnerOrAdminMixin, DeleteView):
    owner_field = 'creator_id'

    def get_queryset(self):
        return Task.objects.visible_to(self.request.user).select_related('project')

    def get_success_url(self):
        return reverse('tasks:board', args=[self.object.project_id])

    def form_valid(self, form):
        messages.success(self.request, f'Tarea "{self.object.title}" eliminada.')
        return super().form_valid(form)


class ChildDeleteView(LoginRequiredMixin, View):
    http_method_names = ['post']
    model = None
    owner_field = None
    anchor = ''
    success_message = ''

    def post(self, request, pk):
        user = request.user
        if user.is_client:
            raise PermissionDenied
        visible_tasks = Task.objects.visible_to(user)
        obj = get_object_or_404(self.model.objects.filter(task__in=visible_tasks), pk=pk)
        if self.owner_field and not (user.is_admin or getattr(obj, self.owner_field) == user.pk):
            raise PermissionDenied

        task_pk = obj.task_id
        self.delete_object(obj)
        messages.success(request, self.success_message)
        return redirect(f"{reverse('tasks:detail', args=[task_pk])}#{self.anchor}")

    def delete_object(self, obj):
        obj.delete()


class SubtaskDeleteView(ChildDeleteView):
    model = Subtask
    anchor = 'subtasks'
    success_message = 'Subtarea eliminada.'


class CommentDeleteView(ChildDeleteView):
    model = Comment
    owner_field = 'author_id'
    anchor = 'comments'
    success_message = 'Comentario eliminado.'


class AttachmentDeleteView(ChildDeleteView):
    model = Attachment
    owner_field = 'uploaded_by_id'
    anchor = 'attachments'
    success_message = 'Adjunto eliminado.'

    def delete_object(self, obj):
        file = obj.file
        obj.delete()
        if file:
            file.delete(save=False)

class MyTasksView(LoginRequiredMixin, TemplateView):
    template_name = 'tasks/my_tasks.html'
    DONE_LIMIT = 8  # en el tablero, «Hecho» muestra solo las más recientes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        week_end = today + timedelta(days=7)
        params = self.request.GET
        not_done = ~Q(status=Task.Status.DONE)

        # `mode` y no `view`: TemplateView ya usa `view` en el contexto
        mode = 'board' if params.get('view') == 'board' else 'list'
        priority = params.get('priority', '')
        priority = priority if priority in Task.Priority.values else ''
        due = params.get('due', '')
        due = due if due in ('overdue', 'week') else ''
        search = params.get('q', '').strip()

        mine = Task.objects.filter(assigned_user=user)

        # Las cifras de arriba no dependen de los filtros
        stats = mine.aggregate(
            open=Count('id', filter=not_done),
            due_week=Count('id', filter=not_done & Q(due_date__range=(today, week_end))),
            overdue=Count('id', filter=not_done & Q(due_date__lt=today)),
            done=Count('id', filter=Q(status=Task.Status.DONE)),
        )

        tasks = mine
        if priority:
            tasks = tasks.filter(priority=priority)
        if due == 'overdue':
            tasks = tasks.filter(not_done, due_date__lt=today)
        elif due == 'week':
            tasks = tasks.filter(not_done, due_date__range=(today, week_end))
        if search:
            tasks = tasks.filter(title__icontains=search)

        tasks = (
            tasks.select_related('project')
            .prefetch_related('tags')
            .annotate(
                subtask_total=Count('subtasks', distinct=True),
                subtask_done=Count('subtasks', filter=Q(subtasks__is_completed=True), distinct=True),
                comment_total=Count('comments', distinct=True),
            )
        )

        status = ''
        if mode == 'list':
            # '' = pendientes (por defecto), 'all' = todas, o un estado concreto
            status = params.get('status', '')
            if status == 'all':
                pass
            elif status in Task.Status.values:
                tasks = tasks.filter(status=status)
            else:
                status = ''
                tasks = tasks.exclude(status=Task.Status.DONE)
            tasks = tasks.order_by(
                'project__name', 'project_id', F('due_date').asc(nulls_last=True), 'id',
            )
        else:
            tasks = tasks.order_by(F('due_date').asc(nulls_last=True), 'id')

        rows = list(tasks)
        for task in rows:
            task.subtask_percent = (
                round(100 * task.subtask_done / task.subtask_total) if task.subtask_total else 0
            )

        groups, columns, done_hidden = [], [], 0
        if mode == 'board':
            by_status = {value: [] for value, _ in Task.Status.choices}
            for task in rows:
                by_status[task.status].append(task)
            done_rows = sorted(by_status['done'], key=attrgetter('updated_at'), reverse=True)
            by_status['done'] = done_rows[:self.DONE_LIMIT]
            done_hidden = len(done_rows) - len(by_status['done'])
            columns = [(value, label, by_status[value]) for value, label in Task.Status.choices]
        else:
            # El queryset ya viene ordenado por proyecto, así que groupby agrupa bien
            for _, items in groupby(rows, key=attrgetter('project_id')):
                items = list(items)
                groups.append({'project': items[0].project, 'tasks': items})

        context.update(
            mode=mode,
            stats=stats,
            total=len(rows),
            overdue_count=stats['overdue'],
            due_week_count=stats['due_week'],
            groups=groups,
            columns=columns,
            done_hidden=done_hidden,
            view_options=filter_options(
                self.request, 'view', [('board', 'Tablero')],
                'board' if mode == 'board' else '', all_label='Lista',
            ),
            status_options=filter_options(
                self.request, 'status', [*Task.Status.choices, ('all', 'Todas')],
                status, all_label='Pendientes',
            ),
            priority_options=filter_options(
                self.request, 'priority', Task.Priority.choices, priority, all_label='Todas',
            ),
            due_options=filter_options(
                self.request, 'due', [('overdue', 'Vencidas'), ('week', 'Esta semana')],
                due, all_label='Todas',
            ),
            q=search,
            has_filters=bool(search or priority or due or status),
            clear_url=f'{self.request.path}?view=board' if mode == 'board' else self.request.path,
            hidden_params=[
                (key, value) for key, value in params.items()
                if key not in ('q', 'page') and value
            ],
            statuses=Task.Status.choices,
            can_move=not user.is_client,
            today=today,
        )
        return context


def my_time_url(day):
    return f"{reverse('tasks:my_time')}?week={day.isoformat()}"


class MyTimeView(LoginRequiredMixin, TemplateView):
    template_name = 'tasks/my_time.html'
    MIN_BAR = 4

    def get_week_start(self, today):
        try:
            day = date.fromisoformat(self.request.GET.get('week', ''))
        except ValueError:
            day = today
        if not 2000 <= day.year <= 2100:
            day = today
        return day - timedelta(days=day.weekday())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        start = self.get_week_start(today)
        end = start + timedelta(days=6)

        logs = list(
            TimeLog.objects.filter(
                user=user,
                date__range=(start, end),
                task__in=Task.objects.visible_to(user),
            )
            .select_related('task__project')
            .order_by('-date', '-created_at')
        )

        per_day = defaultdict(Decimal)
        per_project = defaultdict(Decimal)
        for log in logs:
            per_day[log.date] += log.hours
            per_project[log.task.project] += log.hours

        week_total = sum(per_day.values(), Decimal('0'))
        scale = max(max(per_day.values(), default=Decimal('0')), Decimal('8'))

        days = []
        for offset in range(7):
            day = start + timedelta(days=offset)
            total = per_day.get(day, Decimal('0'))
            percent = max(self.MIN_BAR, round(100 * total / scale)) if total else 0
            days.append({'date': day, 'total': total, 'percent': percent, 'is_today': day == today})

        projects = [
            {'project': project, 'hours': hours, 'percent': round(100 * hours / week_total)}
            for project, hours in sorted(per_project.items(), key=lambda item: item[1], reverse=True)
        ]

        current_start = today - timedelta(days=today.weekday())
        context.update(
            logs=logs,
            days=days,
            projects=projects,
            week_total=week_total,
            days_logged=len(per_day),
            week_start=start,
            week_end=end,
            prev_week=(start - timedelta(days=7)).isoformat(),
            next_week=(start + timedelta(days=7)).isoformat() if start < current_start else None,
            is_current_week=start == current_start,
        )

        if not user.is_client:
            form = QuickTimeLogForm(user=user, initial={'date': today})
            context['quick_form'] = form
            context['open_tasks_count'] = form.fields['task'].queryset.count()
        return context


class MyTimeCreateView(NotClientMixin, View):
    http_method_names = ['post']

    def post(self, request):
        form = QuickTimeLogForm(request.POST, user=request.user)
        if form.is_valid():
            log = form.save(commit=False)
            log.user = request.user
            log.save()
            messages.success(request, 'Tiempo registrado.')
            return redirect(my_time_url(log.date))

        errors = [error for field_errors in form.errors.values() for error in field_errors]
        messages.error(request, ' '.join(errors))
        return redirect('tasks:my_time')


class MyTimeDeleteView(NotClientMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        visible_tasks = Task.objects.visible_to(request.user)
        log = get_object_or_404(TimeLog.objects.filter(task__in=visible_tasks), pk=pk)
        if not (request.user.is_admin or log.user_id == request.user.pk):
            raise PermissionDenied

        day = log.date
        log.delete()
        messages.success(request, 'Registro eliminado.')
        return redirect(my_time_url(day))