import json

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
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from core.permissions import NotClientMixin, OwnerOrAdminMixin
from notifications.models import Notification
from projects.models import Project

from .forms import AttachmentForm, CommentForm, SubtaskForm, TaskForm, TimeLogForm
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

        # Una sola consulta; las tareas se reparten por estado en Python
        by_status = {value: [] for value, _ in Task.Status.choices}
        for task in tasks:
            by_status[task.status].append(task)

        context['columns'] = [
            (value, label, by_status[value]) for value, label in Task.Status.choices
        ]
        context['statuses'] = Task.Status.choices
        context['can_move'] = self.request.user.role != self.request.user.Role.CLIENT
        context['today'] = timezone.localdate()
        return context


class TaskMoveView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        if request.user.role == request.user.Role.CLIENT:
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
            can_edit=self.request.user.role != self.request.user.Role.CLIENT,
            today=today,
        )
        return context


class TaskActionView(LoginRequiredMixin, View):
    """Base para los formularios de la página de detalle.
    Valida, guarda y vuelve al detalle (patrón POST → redirect)."""
    http_method_names = ['post']
    form_class = None
    anchor = ''
    success_message = ''

    def post(self, request, pk):
        if request.user.role == request.user.Role.CLIENT:
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
        if request.user.role == request.user.Role.CLIENT:
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
        status = self.request.GET.get('status')  # lo envía el botón "+" de cada columna
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