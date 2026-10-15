# admin/projects

from django.contrib import admin
from .models import Project

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'status', 
        'owner', 
        'team', 
        'due_date'
    )
    list_filter = (
        'status', 
        'team'
    )
    search_fields = (
        'name',
        'description'
    )
    list_select_related = (
        'owner',
        'team'
    )
    readonly_fields = ('owner', 'created_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.owner = request.user
        super().save_model(request, obj, form, change)