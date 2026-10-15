# admin/tasks

from django.contrib import admin
from .models import Tag, Task, Subtask, Comment, Attachment, TimeLog

class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 1
    fields = ('title', 'is_completed', 'order')

class CommentInline(admin.StackedInline):
    model = Comment
    extra = 0
    fields = ('author', 'content', 'created_at')
    readonly_fields = ('created_at',)
    raw_id_fields = ('author',)

class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ('file_name', 'type', 'file', 'url', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)
    raw_id_fields = ('uploaded_by',)

class TimeLogInline(admin.TabularInline):
    model = TimeLog
    extra = 0
    fields = ('user', 'date', 'hours', 'description')
    raw_id_fields = ('user',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'project',
        'status',
        'priority',
        'assigned_user',
        'due_date'
    )
    list_filter = (
        'status',
        'priority',
        'project',
        'tags'
    )
    search_fields = ('title', 'description')
    list_select_related = ('project', 'assigned_user')
    filter_horizontal = ('tags',)
    raw_id_fields = ('assigned_user',)
    readonly_fields = ('creator', 'created_at', 'updated_at')
    date_hierarchy = 'due_date'
    inlines = [SubtaskInline, CommentInline, AttachmentInline, TimeLogInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color')
    search_fields = ('name',)
    readonly_fields = ('created_at',)

@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'task',
        'is_completed'
    )
    list_filter = ('is_completed',)
    search_fields = (
        'title',
        'task__title'
    )
    list_select_related = ('task',)
    readonly_fields = ('created_at',)

@admin.register(TimeLog)
class TimeLogAdmin(admin.ModelAdmin):
    list_display = (
        'task',
        'user',
        'hours',
        'date'
    )
    list_filter = ('date',)
    search_fields = (
        'task__title',
        'user__username'
    )
    list_select_related = (
        'task',
        'user'
    )
    readonly_fields = ('created_at',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        'author',
        'task',
        'created_at'
    )
    search_fields = (
        'content',
        'author__username',
        'task__title'
    )
    list_select_related = (
        'author',
        'task'
    )
    raw_id_fields = (
        'task',
        'author',
        'parent'
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = (
        'file_name',
        'type',
        'task',
        'uploaded_by'
    )
    list_filter = ('type',)
    search_fields = (
        'file_name',
        'task__title'
    )
    list_select_related = (
        'task',
        'uploaded_by'
    )
    raw_id_fields = (
        'task',
        'uploaded_by'
    )
    readonly_fields = ('created_at',)