from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.permissions import NotClientMixin, OwnerOrAdminMixin
from projects.models import Project

from .forms import TeamForm, TeamMemberForm
from .models import Team, TeamMember


class TeamListView(LoginRequiredMixin, ListView):
    template_name = 'teams/team_list.html'
    context_object_name = 'teams'

    def get_queryset(self):
        return (
            Team.objects.visible_to(self.request.user)
            .select_related('leader')
            .annotate(
                member_count=Count('members', distinct=True),
                project_count=Count('projects', distinct=True),
            )
        )


class TeamDetailView(LoginRequiredMixin, DetailView):
    template_name = 'teams/team_detail.html'
    context_object_name = 'team'

    def get_queryset(self):
        return Team.objects.visible_to(self.request.user).select_related('leader')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = self.object
        can_manage = team.can_be_managed_by(self.request.user)
        context.update(
            memberships=team.teammember_set.select_related('user').order_by('user__first_name', 'user__username'),
            projects=Project.objects.visible_to(self.request.user).filter(team=team).with_task_counts(),
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