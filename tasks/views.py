import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from operator import attrgetter

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Max, Q, Sum
from django.http import JsonResponse
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

    def get_queryset(self):
        return Project.objects.visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        tasks = (
            self.object.tasks
            .select_related('assigned_user', 'assigned_team')
            .prefetch_related('tags')
            .annotate(
                subtask_total=Count('subtasks', distinct=True),
                subtask_done=Count('subtasks', filter=Q(subtasks__is_completed=True), distinct=True),
                comment_total=Count('comments', distinct=True),
            )
            .order_by(F('due_date').asc(nulls_last=True))
        )

        by_status = {value: [] for value, _ in Task.Status.choices}
        for task in tasks:
            by_status[task.status].append(task)

        context['columns'] = [
            (value, label, by_status[value]) for value, label in Task.Status.choices
        ]
        context['statuses'] = Task.Status.choices
        context['can_move'] = not self.request.user.is_client
        context['today'] = timezone.localdate()
        return context


class TaskMoveView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        if request.user.is_client:
            return JsonResponse({'error': 'Sin permiso para mover tareas.'}, status=403)

        task = get_object_or_404(Task.objects.visible_to(request.user), pk=pk)

        try:
            status = json.loads(request.body)['status']
        except (ValueError, KeyError, TypeError):
            return JsonResponse({'error': 'Solicitud inválida.'}, status=400)

        if status not in Task.Status.values:
            return JsonResponse({'error': 'Estado inválido.'}, status=400)

        task.status = status
        task.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'status': task.status, 'label': task.get_status_display()})

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        params = self.request.GET

        tasks = Task.objects.filter(assigned_user=user)

        status = params.get('status', '')
        if status == 'all':
            pass
        elif status in Task.Status.values:
            tasks = tasks.filter(status=status)
        else:
            status = ''
            tasks = tasks.exclude(status=Task.Status.DONE)

        priority = params.get('priority', '')
        if priority in Task.Priority.values:
            tasks = tasks.filter(priority=priority)
        else:
            priority = ''

        search = params.get('q', '').strip()
        if search:
            tasks = tasks.filter(title__icontains=search)

        tasks = list(
            tasks.select_related('project')
            .prefetch_related('tags')
            .order_by('project__name', F('due_date').asc(nulls_last=True), 'id')
        )

        groups = []
        for _, items in groupby(tasks, key=attrgetter('project_id')):
            items = list(items)
            groups.append({'project': items[0].project, 'tasks': items})

        week_end = today + timedelta(days=7)
        context.update(
            groups=groups,
            total=len(tasks),
            overdue_count=sum(1 for task in tasks if task.is_overdue),
            due_week_count=sum(
                1 for task in tasks
                if task.status != Task.Status.DONE and task.due_date and today <= task.due_date <= week_end
            ),
            status_options=filter_options(
                self.request, 'status', [*Task.Status.choices, ('all', 'Todas')],
                status, all_label='Pendientes',
            ),
            priority_options=filter_options(
                self.request, 'priority', Task.Priority.choices, priority, all_label='Todas',
            ),
            current_status=status,
            current_priority=priority,
            q=search,
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