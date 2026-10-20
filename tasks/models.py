# models/tasks

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

class TaskQuerySet(models.QuerySet):
    def visible_to(self, user):
        from projects.models import Project
        return self.filter(project__in=Project.objects.visible_to(user))

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#9C2F52')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'etiqueta'
        verbose_name_plural = 'etiquetas'
        ordering = ['name']

    def __str__(self):
        return self.name


class Task(models.Model):
    class Priority(models.TextChoices):
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    class Status(models.TextChoices):
        TODO = 'todo', 'To-Do'
        DOING = 'doing', 'Doing'
        DONE = 'done', 'Done'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='tasks')
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_tasks',
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks',
    )
    assigned_team = models.ForeignKey(
        'teams.Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = TaskQuerySet.as_manager()

    class Meta:
        verbose_name = 'tarea'
        verbose_name_plural = 'tareas'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['status', 'due_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(estimated_hours__isnull=True) | Q(estimated_hours__gte=0),
                name='tasks_estimated_hours_not_negative',
            ),
            models.CheckConstraint(
                condition=(
                    Q(start_date__isnull=True)
                    | Q(due_date__isnull=True)
                    | Q(due_date__gte=F('start_date'))
                ),
                name='tasks_due_after_start',
            ),
        ]

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('tasks:detail', args=[self.pk])

    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status != self.Status.DONE
            and self.due_date < timezone.localdate()
        )

class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=200)
    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'subtarea'
        verbose_name_plural = 'subtareas'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments',
    )
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'comentario'
        verbose_name_plural = 'comentarios'
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]

    def __str__(self):
        return f'{self.author}: {self.content[:30]}'

class Attachment(models.Model):
    class Type(models.TextChoices):
        DOCUMENT = 'document', 'Document'
        IMAGE = 'image',  'Image'
        LINK = 'link', 'Link'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attachments',
    )
    file_name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.DOCUMENT)
    file = models.FileField(upload_to='attachments/', blank=True, null=True)
    url = models.URLField(max_length=500, blank=True)
    size_kb = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'archivo adjunto'
        verbose_name_plural = 'archivos adjuntos'
        ordering = ['-created_at']

    def __str__(self):
        return self.file_name

class TimeLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_logs',
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'registro de tiempo'
        verbose_name_plural = 'registros de tiempo'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['task', 'date']),
            models.Index(fields=['user', 'date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(hours__gt=0) & Q(hours__lte=24),
                name='tasks_timelog_hours_between_0_and_24',
            ),
        ]

    def __str__(self):
        return f'{self.user} - {self.hours}h'