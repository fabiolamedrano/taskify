# models/notificacions

from django.conf import settings
from django.db import models

class Notification(models.Model):
    class Type(models.TextChoices):
        ASSIGNMENT = 'assignment', 'Assignment'
        DUE_DATE = 'due_date', 'Due Date'
        COMMENT = 'comment', 'Comment'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
    )
    task = models.ForeignKey(
        'tasks.Task', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications',
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'notificación'
        verbose_name_plural = 'notificaciones'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read'])]

    def __str__(self):
        return self.message