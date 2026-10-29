from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import QueryStringMixin, filter_options
from core.permissions import AdminRequiredMixin

from .forms import (
    ProfileForm, SignupForm, StyledPasswordChangeForm, UserCreateForm, UserUpdateForm,
)
from .models import User

class UserListView(AdminRequiredMixin, QueryStringMixin, ListView):
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_role(self):
        role = self.request.GET.get('role', '')
        return role if role in User.Role.values else ''

    def get_active(self):
        active = self.request.GET.get('active', '')
        return active if active in ('1', '0') else ''

    def get_search(self):
        return self.request.GET.get('q', '').strip()

    def search_queryset(self):
        queryset = User.objects.all()
        search = self.get_search()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(first_name__icontains=search)
                | Q(last_name__icontains=search) | Q(email__icontains=search)
            )
        return queryset

    def get_queryset(self):
        queryset = self.search_queryset()
        if self.get_role():
            queryset = queryset.filter(role=self.get_role())
        if self.get_active():
            queryset = queryset.filter(is_active=self.get_active() == '1')
        return queryset.order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role, active, search = self.get_role(), self.get_active(), self.get_search()

        # Los conteos de cada grupo de botones respetan la búsqueda y el OTRO filtro
        base = self.search_queryset()
        by_role = base.filter(is_active=active == '1') if active else base
        by_active = base.filter(role=role) if role else base
        role_counts = dict(by_role.order_by().values_list('role').annotate(n=Count('pk')))
        active_counts = {
            '1': by_active.filter(is_active=True).count(),
            '0': by_active.filter(is_active=False).count(),
        }

        totals = User.objects.aggregate(
            total=Count('id'),
            inactive=Count('id', filter=Q(is_active=False)),
            admins=Count('id', filter=Q(role=User.Role.ADMIN)),
            members=Count('id', filter=Q(role=User.Role.MEMBER)),
            clients=Count('id', filter=Q(role=User.Role.CLIENT)),
        )
        users_url = self.request.path
        context.update(
            cards=[
                {'label': 'Usuarios', 'value': totals['total'], 'unit': '', 'dark': True,
                 'caption': f'{totals["inactive"]} inactivo{"" if totals["inactive"] == 1 else "s"}'
                 if totals['inactive'] else 'Todos activos', 'href': users_url},
                {'label': 'Administradores', 'value': totals['admins'], 'unit': '',
                 'caption': 'Gestionan la plataforma', 'href': f'{users_url}?role=admin'},
                {'label': 'Miembros', 'value': totals['members'], 'unit': '',
                 'caption': 'Crean y editan', 'href': f'{users_url}?role=member'},
                {'label': 'Clientes', 'value': totals['clients'], 'unit': '',
                 'caption': 'Solo lectura', 'href': f'{users_url}?role=client'},
            ],
            role_options=filter_options(
                self.request, 'role', User.Role.choices, role, all_label='Todos', counts=role_counts,
            ),
            active_options=filter_options(
                self.request, 'active', [('1', 'Activos'), ('0', 'Inactivos')], active,
                all_label='Todos', counts=active_counts,
            ),
            q=search,
            has_filters=bool(role or active or search),
            clear_url=users_url,
            hidden_params=[
                (key, value) for key, value in self.request.GET.items()
                if key not in ('q', 'page') and value
            ],
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