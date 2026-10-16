from django.contrib.auth import get_user_model, password_validation
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from rest_framework import serializers

from notifications.models import Notification
from projects.models import Project
from tasks.forms import ALLOWED_EXTENSIONS, MAX_UPLOAD_MB
from tasks.models import Attachment, Comment, Subtask, Tag, Task, TimeLog
from teams.models import Team, TeamMember

User = get_user_model()


def check_date_order(serializer, attrs):
    start = attrs.get('start_date', getattr(serializer.instance, 'start_date', None))
    due = attrs.get('due_date', getattr(serializer.instance, 'due_date', None))
    if start and due and due < start:
        raise serializers.ValidationError(
            {'due_date': 'La fecha límite no puede ser anterior a la de inicio.'}
        )


class TaskScopedMixin:
    def validate_task(self, task):
        if task is None:
            return task
        user = self.context['request'].user
        if not Task.objects.visible_to(user).filter(pk=task.pk).exists():
            raise serializers.ValidationError('No tienes acceso a esa tarea.')
        return task


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=False, style={'input_type': 'password'},
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'avatar', 'is_active', 'password',
        ]

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Es obligatoria al crear un usuario.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name', 'description', 'leader', 'members', 'created_at']
        read_only_fields = ['leader', 'members', 'created_at']


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['id', 'team', 'user', 'role_in_team', 'joined_at']
        read_only_fields = ['joined_at']


class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    done_count = serializers.IntegerField(read_only=True)
    progress = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'objective', 'budget', 'start_date', 'due_date',
            'status', 'owner', 'team', 'task_count', 'done_count', 'progress', 'created_at',
        ]
        read_only_fields = ['owner', 'created_at']

    def validate_budget(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('El presupuesto no puede ser negativo.')
        return value

    def validate(self, attrs):
        check_date_order(self, attrs)
        return attrs


class TagSerializer(serializers.ModelSerializer):
    color = serializers.RegexField(
        r'^#[0-9A-Fa-f]{6}$',
        error_messages={'invalid': 'Usa un color hexadecimal, por ejemplo #9C2F52.'},
    )

    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'created_at']
        read_only_fields = ['created_at']


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'priority', 'status', 'start_date', 'due_date',
            'estimated_hours', 'project', 'creator', 'assigned_user', 'assigned_team',
            'tags', 'created_at', 'updated_at',
        ]
        read_only_fields = ['creator', 'created_at', 'updated_at']

    def validate_project(self, project):
        user = self.context['request'].user
        if not Project.objects.visible_to(user).filter(pk=project.pk).exists():
            raise serializers.ValidationError('No tienes acceso a ese proyecto.')
        return project

    def validate_estimated_hours(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Las horas estimadas no pueden ser negativas.')
        return value

    def validate(self, attrs):
        check_date_order(self, attrs)
        return attrs


class SubtaskSerializer(TaskScopedMixin, serializers.ModelSerializer):
    class Meta:
        model = Subtask
        fields = ['id', 'task', 'title', 'is_completed', 'order', 'created_at']
        read_only_fields = ['created_at']


class CommentSerializer(TaskScopedMixin, serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['id', 'task', 'author', 'parent', 'content', 'created_at', 'updated_at']
        read_only_fields = ['author', 'created_at', 'updated_at']

    def validate(self, attrs):
        task = attrs.get('task', getattr(self.instance, 'task', None))
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        if parent and task and parent.task_id != task.pk:
            raise serializers.ValidationError(
                {'parent': 'La respuesta debe pertenecer a la misma tarea.'}
            )
        return attrs


class AttachmentSerializer(TaskScopedMixin, serializers.ModelSerializer):
    file = serializers.FileField(
        required=False, allow_null=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)],
    )

    class Meta:
        model = Attachment
        fields = [
            'id', 'task', 'uploaded_by', 'file_name', 'type',
            'file', 'url', 'size_kb', 'created_at',
        ]
        read_only_fields = ['uploaded_by', 'type', 'size_kb', 'created_at']
        extra_kwargs = {'file_name': {'required': False}}

    def validate(self, attrs):
        upload = attrs.get('file')
        file = attrs.get('file', getattr(self.instance, 'file', None))
        url = attrs.get('url', getattr(self.instance, 'url', ''))

        if not file and not url:
            raise serializers.ValidationError('Sube un archivo o escribe un enlace.')
        if file and url:
            raise serializers.ValidationError('Elige un archivo o un enlace, no ambos.')

        if upload:
            if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
                raise serializers.ValidationError(
                    {'file': f'El archivo no puede pesar más de {MAX_UPLOAD_MB} MB.'}
                )
            attrs['size_kb'] = max(1, upload.size // 1024)
            is_image = getattr(upload, 'content_type', '').startswith('image/')
            attrs['type'] = Attachment.Type.IMAGE if is_image else Attachment.Type.DOCUMENT
        elif url:
            attrs['type'] = Attachment.Type.LINK

        if not attrs.get('file_name') and not getattr(self.instance, 'file_name', ''):
            attrs['file_name'] = (upload.name if upload else url)[:255]
        return attrs


class TimeLogSerializer(TaskScopedMixin, serializers.ModelSerializer):
    class Meta:
        model = TimeLog
        fields = ['id', 'task', 'user', 'date', 'hours', 'description', 'created_at']
        read_only_fields = ['user', 'created_at']

    def validate_hours(self, value):
        if not 0 < value <= 24:
            raise serializers.ValidationError('Las horas deben estar entre 0 y 24.')
        return value

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError('No puedes registrar tiempo en una fecha futura.')
        return value


class NotificationSerializer(TaskScopedMixin, serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'user', 'task', 'type', 'message', 'is_read', 'created_at']
        read_only_fields = ['user', 'created_at']