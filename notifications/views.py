from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from core.mixins import QueryStringMixin
from tasks.models import Task

from .models import Notification

class NotificationListView(LoginRequiredMixin, QueryStringMixin, ListView):
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 15

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user).select_related('task')
        if self.request.GET.get('filter') == 'unread':
            queryset = queryset.filter(is_read=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['only_unread'] = self.request.GET.get('filter') == 'unread'
        return context

class NotificationOpenView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])

        if notification.task_id and Task.objects.visible_to(request.user).filter(pk=notification.task_id).exists():
            return redirect('tasks:detail', pk=notification.task_id)
        return redirect('notifications:list')

class NotificationMarkAllReadView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, 'Todas las notificaciones quedaron como leídas.')
        return redirect('notifications:list')