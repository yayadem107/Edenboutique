from django.conf import settings
from django.contrib.auth import password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur connecté (GET /api/auth/me/)."""

    role_label = serializers.CharField(source="get_role_display", read_only=True)
    capabilities = serializers.DictField(child=serializers.BooleanField(), read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "full_name", "phone", "role", "role_label",
            "is_active", "must_change_password", "last_login", "capabilities",
        ]
        read_only_fields = fields


class LoginSerializer(TokenObtainPairSerializer):
    """Renvoie les tokens JWT ET le profil, pour éviter un second appel au frontend."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Token de rafraîchissement à révoquer.")


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value


def check_cashier_quota(exclude_pk=None):
    limit = settings.BOUTIQUE["MAX_ACTIVE_CASHIERS"]
    active = User.objects.filter(role=User.Role.CASHIER, is_active=True, is_superuser=False)
    if exclude_pk:
        active = active.exclude(pk=exclude_pk)
    if active.count() >= limit:
        raise serializers.ValidationError(
            {"detail": f"Nombre maximum de caissiers actifs atteint ({limit}). "
                       "Désactivez un compte avant d'en créer ou d'en activer un autre."}
        )


class AdminUserSerializer(serializers.ModelSerializer):
    """Gestion des comptes par l'administrateur."""

    password = serializers.CharField(
        write_only=True, required=False,
        help_text="Obligatoire à la création. L'utilisateur devra le changer à sa première connexion.",
    )
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "full_name", "phone", "role", "role_label", "is_active",
            "must_change_password", "last_login", "date_joined", "password",
        ]
        read_only_fields = ["is_active", "must_change_password", "last_login", "date_joined"]

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "Le mot de passe est obligatoire."})
            password_validation.validate_password(
                attrs["password"], User(username=attrs.get("username"), full_name=attrs.get("full_name", ""))
            )
            if attrs.get("role", User.Role.CASHIER) == User.Role.CASHIER:
                check_cashier_quota()
        else:
            if "password" in attrs:
                raise serializers.ValidationError(
                    {"password": "Utilisez l'action reset-password pour changer un mot de passe."}
                )
            new_role = attrs.get("role", self.instance.role)
            if self.instance.role == User.Role.ADMIN and new_role != User.Role.ADMIN:
                others = User.objects.filter(role=User.Role.ADMIN, is_active=True).exclude(pk=self.instance.pk)
                if not others.exists():
                    raise serializers.ValidationError({"role": "Il doit rester au moins un administrateur actif."})
            if new_role == User.Role.CASHIER and self.instance.role != User.Role.CASHIER and self.instance.is_active:
                check_cashier_quota(exclude_pk=self.instance.pk)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data, must_change_password=True)
        user.set_password(password)
        user.save()
        return user
