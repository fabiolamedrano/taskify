from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Sum
from django.utils import timezone
from django.views.generic import DetailView, ListView

from tasks.models import TimeLog

from .models import Project


class ProjectListView(LoginRequiredMixin, ListView):
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        queryset = (
            Project.objects.visible_to(self.request.user)
            .select_related('owner', 'team')
            .with_task_counts()
        )
        status = self.request.GET.get('status')
        if status in Project.Status.values:
            queryset = queryset.filter(status=status)
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Project.Status.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['q'] = self.request.GET.get('q', '').strip()
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

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

        context['tasks'] = list(
            project.tasks
            .select_related('assigned_user', 'assigned_team')
            .prefetch_related('tags')
            .order_by(F('due_date').asc(nulls_last=True))
        )
        context['estimated_hours'] = (
            project.tasks.aggregate(total=Sum('estimated_hours'))['total'] or 0
        )
        context['logged_hours'] = (
            TimeLog.objects.filter(task__project=project).aggregate(total=Sum('hours'))['total'] or 0
        )
        context['members'] = project.team.members.all() if project.team else []
        context['today'] = timezone.localdate()
        return context