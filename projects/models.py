# models/projects

from django.conf import settings
from django.db import models
from django.db.models import Count, F, Q
from django.urls import reverse

class ProjectQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.is_admin:
            return self
        visible_ids = self.model.objects.filter(
            Q(owner=user) | Q(team__members=user) | Q(tasks__assigned_user=user)
        ).values('id')
        return self.filter(id__in=visible_ids)

    def with_task_counts(self):
        return self.annotate(
            task_count=Count('tasks'),
            done_count=Count('tasks', filter=Q(tasks__status='done')),
        )

class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    objective = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_projects',
    )
    team = models.ForeignKey(
        'teams.Team', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='projects',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        verbose_name = 'proyecto'
        verbose_name_plural = 'proyectos'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status'])]
        constraints = [
            models.CheckConstraint(
                condition=Q(budget__isnull=True) | Q(budget__gte=0),
                name='projects_budget_not_negative',
            ),
            models.CheckConstraint(
                condition=(
                    Q(start_date__isnull=True)
                    | Q(due_date__isnull=True)
                    | Q(due_date__gte=F('start_date'))
                ),
                name='projects_due_after_start',
            ),
        ]

    @property
    def progress(self):
        if not self.task_count:
            return 0
        return round(100 * self.done_count / self.task_count)
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('projects:detail', args=[self.pk])