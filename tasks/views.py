import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from projects.models import Project

from .models import Task


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