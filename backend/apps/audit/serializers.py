from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "username", "action", "action_label", "target_type",
            "target_id", "target_repr", "details", "ip_address", "user_agent", "created_at",
        ]
