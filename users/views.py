from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import QueryStringMixin
from core.permissions import AdminRequiredMixin

from .forms import UserCreateForm, UserUpdateForm
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