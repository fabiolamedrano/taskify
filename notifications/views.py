from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from core.mixins import QueryStringMixin, filter_options
from tasks.models import Task

from .models import Notification


def safe_next(request):
    """Dirección a la que volver tras una acción, solo si es de este mismo sitio."""
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return next_url
    return ''


def day_label(moment, today):
    day = timezone.localtime(moment).date()
    if day == today:
        return 'Hoy'
    if day == today - timedelta(days=1):
        return 'Ayer'
    return date_format(day, 'j M Y')


class NotificationListView(LoginRequiredMixin, QueryStringMixin, ListView):
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 15

    def get_filters(self):
        kind = self.request.GET.get('type', '')
        kind = kind if kind in Notification.Type.values else ''
        return kind, self.request.GET.get('filter') == 'unread'

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user).select_related('task')
        kind, only_unread = self.get_filters()
        if kind:
            queryset = queryset.filter(type=kind)
        if only_unread:
            queryset = queryset.filter(is_read=False)
        return queryset.order_by('-created_at', '-id')

    def paginate_queryset(self, queryset, page_size):
        try:
            return super().paginate_queryset(queryset, page_size)
        except Http404:
            # Una página que ya no existe (por ejemplo, tras marcar el último aviso
            # de ella como leído) muestra la última en lugar de un error
            paginator = self.get_paginator(
                queryset, page_size, orphans=self.get_paginate_orphans(),
                allow_empty_first_page=self.get_allow_empty(),
            )
            page = paginator.page(paginator.num_pages)
            return paginator, page, page.object_list, page.has_other_pages()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        kind, only_unread = self.get_filters()
        today = timezone.localdate()

        notifications = list(context['notifications'])
        for notification in notifications:
            notification.day_label = day_label(notification.created_at, today)
        context['notifications'] = notifications

        unread = dict(
            Notification.objects.filter(user=self.request.user, is_read=False)
            .order_by().values_list('type').annotate(n=Count('pk'))
        )
        base = reverse('notifications:list')
        context.update(
            cards=[
                {'label': 'Sin leer', 'value': sum(unread.values()), 'unit': '', 'dark': True,
                 'caption': 'Avisos pendientes', 'href': f'{base}?filter=unread'},
                {'label': 'Asignaciones', 'value': unread.get(Notification.Type.ASSIGNMENT, 0), 'unit': '',
                 'caption': 'Tareas que te asignaron', 'href': f'{base}?type=assignment&filter=unread'},
                {'label': 'Vencimientos', 'value': unread.get(Notification.Type.DUE_DATE, 0), 'unit': '',
                 'caption': 'Fechas por vencer o vencidas', 'href': f'{base}?type=due_date&filter=unread'},
                {'label': 'Comentarios', 'value': unread.get(Notification.Type.COMMENT, 0), 'unit': '',
                 'caption': 'Nuevas respuestas', 'href': f'{base}?type=comment&filter=unread'},
            ],
            state_options=filter_options(
                self.request, 'filter', [('unread', 'Sin leer')],
                'unread' if only_unread else '', all_label='Todas',
            ),
            type_options=filter_options(
                self.request, 'type', Notification.Type.choices, kind, all_label='Todos',
            ),
            has_filters=bool(kind or only_unread),
        )
        return context


class NotificationOpenView(LoginRequiredMixin, View):
    """Marca la notificación como leída y abre la tarea relacionada."""
    http_method_names = ['post']

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])

        # Solo se redirige a la tarea si el usuario todavía puede verla
        if notification.task_id and Task.objects.visible_to(request.user).filter(pk=notification.task_id).exists():
            return redirect('tasks:detail', pk=notification.task_id)
        return redirect('notifications:list')


class NotificationMarkReadView(LoginRequiredMixin, View):
    """Marca una notificación como leída sin abrir la tarea."""
    http_method_names = ['post']

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return redirect(safe_next(request) or 'notifications:list')


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, 'Todas las notificaciones quedaron como leídas.')
        return redirect(safe_next(request) or 'notifications:list')