from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "full_name", "role", "is_active", "last_login"]
    list_filter = ["role", "is_active"]
    search_fields = ["username", "full_name", "phone"]
    ordering = ["full_name"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informations", {"fields": ("full_name", "phone", "email")}),
        ("Rôle et accès", {"fields": ("role", "is_active", "must_change_password")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "full_name", "role", "password1", "password2"),
        }),
    )
