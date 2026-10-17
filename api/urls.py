# urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

router = DefaultRouter()
router.register('users', views.UserViewSet, basename='user')
router.register('teams', views.TeamViewSet, basename='team')
router.register('team-members', views.TeamMemberViewSet, basename='teammember')
router.register('projects', views.ProjectViewSet, basename='project')
router.register('tags', views.TagViewSet, basename='tag')
router.register('tasks', views.TaskViewSet, basename='task')
router.register('subtasks', views.SubtaskViewSet, basename='subtask')
router.register('comments', views.CommentViewSet, basename='comment')
router.register('attachments', views.AttachmentViewSet, basename='attachment')
router.register('time-logs', views.TimeLogViewSet, basename='timelog')
router.register('notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]