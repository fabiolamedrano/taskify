from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Sum
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.permissions import NotClientMixin, OwnerOrAdminMixin
from core.mixins import QueryStringMixin, filter_options
from tasks.models import TimeLog

from .forms import ProjectForm
from .models import Project


class ProjectListView(LoginRequiredMixin, QueryStringMixin, ListView):
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 12

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
        return queryset.order_by('-created_at', '-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get('status', '')
        status = status if status in Project.Status.values else ''
        context['status_options'] = filter_options(
            self.request, 'status', Project.Status.choices, status, all_label='Todos',
        )
        context['current_status'] = status
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