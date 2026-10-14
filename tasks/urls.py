from django.urls import path

from .views import BoardView, TaskMoveView

app_name = 'tasks'

urlpatterns = [
    path('projects/<int:project_pk>/board/', BoardView.as_view(), name='board'),
    path('tasks/<int:pk>/move/', TaskMoveView.as_view(), name='move'),
]