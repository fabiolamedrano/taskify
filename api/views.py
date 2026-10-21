# views.py

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from notifications.models import Notification
from projects.models import Project
from tasks.models import Attachment, Comment, Subtask, Tag, Task, TimeLog
from teams.models import Team, TeamMember

from .permissions import IsAdminOrReadOnly, NotClientOrReadOnly, OwnerOrAdminForWrite, is_admin
from .serializers import (
    AttachmentSerializer, CommentSerializer, NotificationSerializer, ProjectSerializer,
    SubtaskSerializer, TagSerializer, TaskSerializer, TeamMemberSerializer, TeamSerializer,
    TimeLogSerializer, UserSerializer,
)

User = get_user_model()

class BaseModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, NotClientOrReadOnly, OwnerOrAdminForWrite]
    owner_field = None


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering_fields = ['username', 'date_joined']

    def get_queryset(self):
        user = self.request.user
        if is_admin(user):
            return User.objects.all()
        return User.objects.filter(
            Q(pk=user.pk) | Q(teams__in=user.teams.all())
        ).distinct()


class TeamViewSet(BaseModelViewSet):
    serializer_class = TeamSerializer
    owner_field = 'leader_id'
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return Team.objects.visible_to(self.request.user).select_related('leader').prefetch_related('members')

    def perform_create(self, serializer):
        team = serializer.save(leader=self.request.user)
        TeamMember.objects.get_or_create(
            team=team, user=self.request.user, defaults={'role_in_team': 'Líder'},
        )


class TeamMemberViewSet(BaseModelViewSet):
    serializer_class = TeamMemberSerializer
    owner_field = 'team.leader_id'
    filterset_fields = ['team', 'user']

    def get_queryset(self):
        return TeamMember.objects.filter(
            team__in=Team.objects.visible_to(self.request.user)
        ).select_related('team', 'user')
    
    def _check_manager(self, team):
        user = self.request.user
        if not (is_admin(user) or team.leader_id == user.pk):
            raise PermissionDenied('Solo el líder del equipo puede administrar sus miembros.')

    def perform_create(self, serializer):
        self._check_manager(serializer.validated_data['team'])
        serializer.save()

    def perform_update(self, serializer):
        if 'team' in serializer.validated_data:
            self._check_manager(serializer.validated_data['team'])
        serializer.save()


class ProjectViewSet(BaseModelViewSet):
    serializer_class = ProjectSerializer
    owner_field = 'owner_id'
    filterset_fields = ['status', 'team', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'due_date', 'created_at']

    def get_queryset(self):
        return (
            Project.objects.visible_to(self.request.user)
            .select_related('owner', 'team')
            .with_task_counts()
            .order_by('-created_at', '-id')
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    search_fields = ['name']


class TaskViewSet(BaseModelViewSet):
    serializer_class = TaskSerializer
    owner_field = 'creator_id'
    owner_methods = ('DELETE',)
    filterset_fields = ['project', 'status', 'priority', 'assigned_user', 'assigned_team', 'tags']
    search_fields = ['title', 'description']
    ordering_fields = ['due_date', 'created_at', 'title']

    def get_queryset(self):
        return (
            Task.objects.visible_to(self.request.user)
            .select_related('project', 'creator', 'assigned_user', 'assigned_team')
            .prefetch_related('tags')
        )

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class SubtaskViewSet(BaseModelViewSet):
    serializer_class = SubtaskSerializer
    filterset_fields = ['task', 'is_completed']
    ordering_fields = ['order', 'created_at']

    def get_queryset(self):
        return Subtask.objects.filter(task__in=Task.objects.visible_to(self.request.user))


class CommentViewSet(BaseModelViewSet):
    serializer_class = CommentSerializer
    owner_field = 'author_id'
    filterset_fields = ['task', 'author']
    search_fields = ['content']
    ordering_fields = ['created_at']

    def get_queryset(self):
        return Comment.objects.filter(
            task__in=Task.objects.visible_to(self.request.user)
        ).select_related('author')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class AttachmentViewSet(BaseModelViewSet):
    serializer_class = AttachmentSerializer
    owner_field = 'uploaded_by_id'
    filterset_fields = ['task', 'type', 'uploaded_by']
    search_fields = ['file_name']

    def get_queryset(self):
        return Attachment.objects.filter(
            task__in=Task.objects.visible_to(self.request.user)
        ).select_related('uploaded_by')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class TimeLogViewSet(BaseModelViewSet):
    serializer_class = TimeLogSerializer
    owner_field = 'user_id'
    filterset_fields = ['task', 'user', 'date']
    ordering_fields = ['date', 'hours', 'created_at']

    def get_queryset(self):
        return TimeLog.objects.filter(
            task__in=Task.objects.visible_to(self.request.user)
        ).select_related('user')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['type', 'is_read']
    ordering_fields = ['created_at']

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related('task')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)