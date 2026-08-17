from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["email", "username", "full_name", "role", "school", "is_active", "created_at"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "username", "first_name", "last_name", "school"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = UserAdmin.fieldsets + (
        ("LearnLeague", {"fields": ("role", "avatar", "school", "subject_specialty", "bio")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("LearnLeague", {"fields": ("email", "first_name", "last_name", "role", "school")}),
    )
