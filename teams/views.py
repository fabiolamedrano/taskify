from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.formatting import plain, plural
from core.mixins import QueryStringMixin
from core.permissions import NotClientMixin, OwnerOrAdminMixin
from projects.models import Project
from tasks.models import Task, TimeLog

from .forms import TeamForm, TeamMemberForm
from .models import Team, TeamMember

class TeamListView(LoginRequiredMixin, QueryStringMixin, ListView):
    template_name = 'teams/team_list.html'
    context_object_name = 'teams'
    paginate_by = 12
    PREVIEW = 5  # avatares que se muestran en cada tarjeta

    def get_search(self):
        return self.request.GET.get('q', '').strip()

    def get_queryset(self):
        queryset = (
            Team.objects.visible_to(self.request.user)
            .select_related('leader')
            .annotate(
                member_count=Count('members', distinct=True),
                project_count=Count('projects', distinct=True),
            )
            .prefetch_related(Prefetch(
                'teammember_set',
                queryset=TeamMember.objects.select_related('user').order_by('user__first_name', 'user__username'),
                to_attr='memberships',
            ))
        )
        search = self.get_search()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        visible = Team.objects.visible_to(user)

        teams = list(context['teams'])
        # Tareas abiertas por equipo, en una sola consulta para toda la página
        open_by_team = dict(
            Task.objects.visible_to(user)
            .filter(project__team__in=[team.pk for team in teams])
            .exclude(status=Task.Status.DONE)
            .order_by().values_list('project__team').annotate(n=Count('pk'))
        )
        for team in teams:
            team.preview = [membership.user for membership in team.memberships[:self.PREVIEW]]
            team.extra_members = len(team.memberships) - len(team.preview)
            team.open_tasks = open_by_team.get(team.pk, 0)
        context['teams'] = teams

        projects = Project.objects.visible_to(user).filter(team__in=visible)
        open_tasks = (
            Task.objects.visible_to(user).filter(project__team__in=visible)
            .exclude(status=Task.Status.DONE)
        )
        people = TeamMember.objects.filter(team__in=visible).values('user').distinct().count()
        context.update(
            cards=[
                {'label': 'Equipos', 'value': visible.count(), 'unit': '', 'dark': True,
                 'caption': 'A los que tienes acceso', 'href': '#teams'},
                {'label': 'Personas', 'value': people, 'unit': '',
                 'caption': 'En tus equipos', 'href': '#teams'},
                {'label': 'Proyectos', 'value': projects.count(), 'unit': '',
                 'caption': 'Asignados a equipos', 'href': reverse('projects:list')},
                {'label': 'Tareas abiertas', 'value': open_tasks.count(), 'unit': '',
                 'caption': 'En los proyectos de tus equipos', 'href': '#teams'},
            ],
            q=self.get_search(),
            clear_search_url=self.request.path,
        )
        return context


class TeamDetailView(LoginRequiredMixin, DetailView):
    template_name = 'teams/team_detail.html'
    context_object_name = 'team'

    def get_queryset(self):
        return Team.objects.visible_to(self.request.user).select_related('leader')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = self.object
        user = self.request.user
        today = timezone.localdate()
        can_manage = team.can_be_managed_by(user)

        memberships = list(
            team.teammember_set.select_related('user').order_by('user__first_name', 'user__username')
        )
        tasks = Task.objects.visible_to(user).filter(project__team=team)
        not_done = ~Q(status=Task.Status.DONE)
        overall = tasks.aggregate(
            open=Count('id', filter=not_done),
            overdue=Count('id', filter=not_done & Q(due_date__lt=today)),
        )
        per_user = {
            row['assigned_user_id']: row
            for row in tasks.order_by().values('assigned_user_id').annotate(
                total=Count('id'), done=Count('id', filter=Q(status=Task.Status.DONE)),
            )
        }
        for membership in memberships:
            row = per_user.get(membership.user_id, {'total': 0, 'done': 0})
            membership.total = row['total']
            membership.done = row['done']
            membership.percent = round(100 * row['done'] / row['total']) if row['total'] else 0

        month_hours = TimeLog.objects.filter(
            task__in=tasks, date__gte=today.replace(day=1),
        ).aggregate(total=Sum('hours'))['total'] or Decimal('0')

        projects = list(
            Project.objects.visible_to(user).filter(team=team)
            .with_task_counts().order_by('-created_at', '-id')
        )
        active = sum(1 for project in projects if project.status == Project.Status.ACTIVE)
        leader = team.leader

        context.update(
            cards=[
                {'label': 'Miembros', 'value': len(memberships), 'unit': '', 'dark': True, 'href': '#members',
                 'caption': f'Líder: {leader.get_full_name() or leader.username}' if leader else 'Sin líder'},
                {'label': 'Proyectos', 'value': len(projects), 'unit': '', 'href': '#projects',
                 'caption': f'{active} activo{"" if active == 1 else "s"}'},
                {'label': 'Tareas abiertas', 'value': overall['open'], 'unit': '', 'href': '#members',
                 'caption': plural(overall['overdue'], 'vencida') if overall['overdue'] else 'Ninguna vencida'},
                {'label': 'Horas del mes', 'value': plain(month_hours), 'unit': ' h', 'href': '#projects',
                 'caption': 'Registradas en sus proyectos'},
            ],
            memberships=memberships,
            projects=projects,
            project_count=len(projects),
            can_manage=can_manage,
            member_form=TeamMemberForm(team=team) if can_manage else None,
        )
        return context


class TeamCreateView(NotClientMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = 'teams/team_form.html'

    @transaction.atomic
    def form_valid(self, form):
        form.instance.leader = self.request.user
        response = super().form_valid(form)
        TeamMember.objects.get_or_create(
            team=self.object, user=self.request.user, defaults={'role_in_team': 'Líder'},
        )
        messages.success(self.request, 'Equipo creado.')
        return response


class TeamUpdateView(NotClientMixin, OwnerOrAdminMixin, UpdateView):
    form_class = TeamForm
    template_name = 'teams/team_form.html'
    owner_field = 'leader_id'

    def get_queryset(self):
        return Team.objects.visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Equipo actualizado.')
        return super().form_valid(form)


class TeamDeleteView(NotClientMixin, OwnerOrAdminMixin, DeleteView):
    template_name = 'teams/team_confirm_delete.html'
    owner_field = 'leader_id'
    success_url = reverse_lazy('teams:list')

    def get_queryset(self):
        return Team.objects.visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project_count'] = self.object.projects.count()
        context['task_count'] = self.object.assigned_tasks.count()
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Equipo "{self.object.name}" eliminado.')
        return super().form_valid(form)


class TeamMemberAddView(NotClientMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        team = get_object_or_404(Team.objects.visible_to(request.user), pk=pk)
        if not team.can_be_managed_by(request.user):
            raise PermissionDenied

        form = TeamMemberForm(request.POST, team=team)
        if form.is_valid():
            membership = form.save(commit=False)
            membership.team = team
            membership.save()
            name = membership.user.get_full_name() or membership.user.username
            messages.success(request, f'{name} se unió al equipo.')
        else:
            errors = [error for field_errors in form.errors.values() for error in field_errors]
            messages.error(request, ' '.join(errors))
        return redirect(team)


class TeamMemberRemoveView(NotClientMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        membership = get_object_or_404(
            TeamMember.objects.select_related('team', 'user')
            .filter(team__in=Team.objects.visible_to(request.user)),
            pk=pk,
        )
        team = membership.team
        if not team.can_be_managed_by(request.user):
            raise PermissionDenied

        if membership.user_id == team.leader_id:
            messages.error(request, 'No puedes quitar al líder del equipo. Cambia primero el líder.')
        else:
            membership.delete()
            messages.success(request, 'Miembro eliminado del equipo.')
        return redirect(team)