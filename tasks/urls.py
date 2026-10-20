from django.urls import path

from .views import (
    AttachmentCreateView, AttachmentDeleteView, BoardView, CommentCreateView,
    CommentDeleteView, MyTasksView, MyTimeCreateView, MyTimeDeleteView, MyTimeView,
    SubtaskCreateView, SubtaskDeleteView, SubtaskToggleView, TaskCreateView,
    TaskDeleteView, TaskDetailView, TaskMoveView, TaskUpdateView, TimeLogCreateView,
)

app_name = 'tasks'

urlpatterns = [
    path('my-tasks/', MyTasksView.as_view(), name='mine'),
    path('time/', MyTimeView.as_view(), name='my_time'),
    path('time/add/', MyTimeCreateView.as_view(), name='my_time_add'),
    path('time/<int:pk>/delete/', MyTimeDeleteView.as_view(), name='my_time_delete'),
    path('projects/<int:project_pk>/board/', BoardView.as_view(), name='board'),
    path('projects/<int:project_pk>/tasks/new/', TaskCreateView.as_view(), name='create'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='detail'),
    path('tasks/<int:pk>/edit/', TaskUpdateView.as_view(), name='update'),
    path('tasks/<int:pk>/delete/', TaskDeleteView.as_view(), name='delete'),
    path('tasks/<int:pk>/move/', TaskMoveView.as_view(), name='move'),
    path('tasks/<int:pk>/subtasks/add/', SubtaskCreateView.as_view(), name='subtask_add'),
    path('tasks/<int:pk>/comments/add/', CommentCreateView.as_view(), name='comment_add'),
    path('tasks/<int:pk>/time/add/', TimeLogCreateView.as_view(), name='timelog_add'),
    path('tasks/<int:pk>/attachments/add/', AttachmentCreateView.as_view(), name='attachment_add'),
    path('subtasks/<int:pk>/toggle/', SubtaskToggleView.as_view(), name='subtask_toggle'),
    path('subtasks/<int:pk>/delete/', SubtaskDeleteView.as_view(), name='subtask_delete'),
    path('comments/<int:pk>/delete/', CommentDeleteView.as_view(), name='comment_delete'),
    path('attachments/<int:pk>/delete/', AttachmentDeleteView.as_view(), name='attachment_delete'),
]