from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Vérifie que l'API et la base de données répondent (utile pour Docker et le frontend)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Système"],
        responses=inline_serializer(
            "Health",
            {
                "status": serializers.CharField(),
                "database": serializers.CharField(),
                "boutique": serializers.CharField(),
                "currency": serializers.CharField(),
            },
        ),
    )
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response(
            {
                "status": "ok",
                "database": connection.vendor,
                "boutique": settings.BOUTIQUE["NAME"],
                "currency": settings.BOUTIQUE["CURRENCY"],
            }
        )
