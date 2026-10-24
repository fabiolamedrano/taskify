from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import QueryStringMixin
from core.permissions import AdminRequiredMixin

from .forms import (
    ProfileForm, SignupForm, StyledPasswordChangeForm, UserCreateForm, UserUpdateForm,
)
from .models import User

class UserListView(AdminRequiredMixin, QueryStringMixin, ListView):
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.all()
        role = self.request.GET.get('role')
        if role in User.Role.values:
            queryset = queryset.filter(role=role)
        active = self.request.GET.get('active')
        if active in ('1', '0'):
            queryset = queryset.filter(is_active=active == '1')
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(first_name__icontains=search)
                | Q(last_name__icontains=search) | Q(email__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            roles=User.Role.choices,
            current_role=self.request.GET.get('role', ''),
            current_active=self.request.GET.get('active', ''),
            q=self.request.GET.get('q', '').strip(),
        )
        return context

class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Usuario {self.object.username} creado.')
        return response

class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['current_user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f'Usuario {self.object.username} actualizado.')
        return super().form_valid(form)

class SignupView(CreateView):
    form_class = SignupForm
    template_name = 'registration/signup.html'

    def dispatch(self, request, *args, **kwargs):
        if not settings.ALLOW_SIGNUP:
            raise Http404
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(
            self.request,
            f'¡Bienvenido a Taskify, {user.first_name or user.username}! Todavía no estás en ningún '
            'equipo: crea tu primer proyecto o pide a un administrador que te agregue a uno.',
        )
        return redirect('dashboard')


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = 'users/profile.html'
    success_url = reverse_lazy('users:profile')

    def get_object(self, queryset=None):
        # Siempre la cuenta de quien tiene la sesión: no hay forma de editar la de otra persona
        return User.objects.get(pk=self.request.user.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['teams'] = self.object.teams.order_by('name')
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Perfil actualizado.')
        return super().form_valid(form)


class AccountPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = 'users/password_change.html'
    success_url = reverse_lazy('users:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Contraseña actualizada.')
        return super().form_valid(form)  # mantiene la sesión abierta