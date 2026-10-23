from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "type", "type_label", "level", "title", "message", "data",
            "is_read", "read_at", "created_at",
        ]
        read_only_fields = fields
