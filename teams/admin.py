from django.contrib import admin
from .models import Team, TeamMember

class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1
    fields = ('user', 'role_in_team', 'joined_at')
    readonly_fields = ('joined_at')
    raw_id_fields = ('user', )

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'leader', 
        'created_at'
    )
    search_fields = ('name',)
    list_select_related = ('leader',)
    raw_id_fields = ('leader',)