from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        MEMBER = 'member', 'Member'
        CLIENT = 'client', 'Client'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    class Meta:
        ordering = ['username']