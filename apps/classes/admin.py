from django.contrib import admin

from .models import ClassRoom


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'subject', 'education_level', 'teacher', 'color', 'created_at']
    list_filter = ['education_level', 'created_at']
    search_fields = ['name', 'subject', 'teacher__username', 'teacher__email']
    ordering = ['-created_at']
    raw_id_fields = ['teacher']
