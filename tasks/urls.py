from django.urls import path

from django.conf import settings
from django.conf.urls.static import static

from .views import (
    AttachmentCreateView, BoardView, CommentCreateView, SubtaskCreateView,
    SubtaskToggleView, TaskDetailView, TaskMoveView, TimeLogCreateView,
)

app_name = 'tasks'

urlpatterns = [
    path('projects/<int:project_pk>/board/', BoardView.as_view(), name='board'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='detail'),
    path('tasks/<int:pk>/move/', TaskMoveView.as_view(), name='move'),
    path('tasks/<int:pk>/subtasks/add/', SubtaskCreateView.as_view(), name='subtask_add'),
    path('tasks/<int:pk>/comments/add/', CommentCreateView.as_view(), name='comment_add'),
    path('tasks/<int:pk>/time/add/', TimeLogCreateView.as_view(), name='timelog_add'),
    path('tasks/<int:pk>/attachments/add/', AttachmentCreateView.as_view(), name='attachment_add'),
    path('subtasks/<int:pk>/toggle/', SubtaskToggleView.as_view(), name='subtask_toggle'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)