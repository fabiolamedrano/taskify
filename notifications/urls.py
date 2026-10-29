from django.urls import path

from .views import (
    NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView,
    NotificationOpenView,
)

app_name = 'notifications'

urlpatterns = [
    path('', NotificationListView.as_view(), name='list'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='read_all'),
    path('<int:pk>/open/', NotificationOpenView.as_view(), name='open'),
    path('<int:pk>/read/', NotificationMarkReadView.as_view(), name='mark_read'),
]