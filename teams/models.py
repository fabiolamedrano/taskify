# models/teams

from django.conf import settings
from django.db import models

class Team(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='led_teams'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='TeamMember', related_name='teams',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'equipo'
        verbose_name_plural = 'equipos'
        ordering = ['name']

    def __str__(self):
        return self.name

class TeamMember(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    role_in_team = models.CharField(max_length=50, blank=True)
    joined_at = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = 'miembro de equipo'
        verbose_name_plural = 'miembros de equipo'
        constraints = [
            models.UniqueConstraint(fields=['user', 'team'], name='teams_unique_team_member'),
        ]

    def __str__(self):
        return f'{self.user} in {self.team}'