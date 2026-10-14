from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'type',
        'message',
        'is_read',
        'created_at'
    )
    list_filter = (
        'type',
        'is_read'
    )
    search_fields = (
        'message',
        'user__username'
    )
    list_select_related = ('user',)
    raw_id_fields = ('user', 'task')
    readonly_fields = ('created_at',)