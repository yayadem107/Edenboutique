from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "recipient", "type", "level", "title", "is_read"]
    list_filter = ["type", "level", "is_read"]
    search_fields = ["title", "message"]
