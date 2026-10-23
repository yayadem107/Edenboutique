from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.common.permissions import IsAdmin
from apps.notifications.models import Notification
from apps.notifications.services import notify_admins

from .models import User
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    ResetPasswordSerializer,
    TokenPairSerializer,
    UserSerializer,
    check_cashier_quota,
)
from .services import revoke_all_tokens


def new_token_pair(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@extend_schema(tags=["Authentification"])
class LoginView(TokenObtainPairView):
    """Connexion par identifiant + mot de passe. Limité à 10 tentatives par minute."""

    serializer_class = LoginSerializer
    throttle_scope = "login"

    @extend_schema(summary="Se connecter", responses=LoginResponseSerializer)
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            log_action(AuditLog.Action.LOGIN_FAILED, request=request,
                       username=str(request.data.get("username", ""))[:150])
            raise
        user = User.objects.get(pk=response.data["user"]["id"])
        log_action(AuditLog.Action.LOGIN, user=user, request=request)
        return response


@extend_schema(tags=["Authentification"])
class RefreshView(TokenRefreshView):
    @extend_schema(summary="Renouveler le token d'accès", responses=TokenPairSerializer)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Authentification"])
class LogoutView(APIView):
    @extend_schema(summary="Se déconnecter", request=LogoutSerializer,
                   responses={204: OpenApiResponse(description="Déconnecté")})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # Token déjà expiré ou révoqué : la déconnexion est quand même effective.
        log_action(AuditLog.Action.LOGOUT, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Authentification"])
class MeView(APIView):
    @extend_schema(summary="Profil et droits de l'utilisateur connecté", responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema(tags=["Authentification"])
class ChangePasswordView(APIView):
    @extend_schema(
        summary="Changer son mot de passe",
        description="Déconnecte les autres appareils et renvoie de nouveaux tokens.",
        request=ChangePasswordSerializer,
        responses=TokenPairSerializer,
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save()
        revoke_all_tokens(user)
        log_action(AuditLog.Action.PASSWORD_CHANGED, request=request, target=user)
        return Response(new_token_pair(user))


@extend_schema_view(
    list=extend_schema(summary="Liste des comptes"),
    create=extend_schema(summary="Créer un compte (caissier ou administrateur)"),
    retrieve=extend_schema(summary="Détail d'un compte"),
    update=extend_schema(summary="Modifier un compte"),
    partial_update=extend_schema(summary="Modifier partiellement un compte"),
)
@extend_schema(tags=["Utilisateurs (admin)"])
class UserViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Les comptes ne sont jamais supprimés (l'historique des ventes doit rester lisible) :
    on les désactive.
    """

    queryset = User.objects.all()
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ["role", "is_active"]
    search_fields = ["username", "full_name", "phone"]
    ordering_fields = ["full_name", "date_joined", "last_login"]

    def perform_create(self, serializer):
        user = serializer.save()
        log_action(AuditLog.Action.CREATE, request=self.request, target=user,
                   details={"role": user.role})

    def perform_update(self, serializer):
        user = serializer.save()
        log_action(AuditLog.Action.UPDATE, request=self.request, target=user,
                   details={k: str(v) for k, v in serializer.validated_data.items()})

    @extend_schema(summary="Réinitialiser le mot de passe d'un compte", request=ResetPasswordSerializer,
                   responses={204: OpenApiResponse(description="Mot de passe réinitialisé")})
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = True
        user.save()
        revoke_all_tokens(user)
        log_action(AuditLog.Action.PASSWORD_RESET, request=request, target=user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Désactiver un compte (bloque la connexion)", request=None,
                   responses=AdminUserSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "Vous ne pouvez pas désactiver votre propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save()
        revoke_all_tokens(user)
        log_action(AuditLog.Action.UPDATE, request=request, target=user, details={"is_active": False})
        notify_admins(Notification.Type.SENSITIVE_ACTION, "Compte désactivé",
                      f"Le compte de {user} a été désactivé par {request.user}.",
                      level=Notification.Level.WARNING, exclude=request.user)
        return Response(self.get_serializer(user).data)

    @extend_schema(summary="Réactiver un compte", request=None, responses=AdminUserSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        if not user.is_active and user.role == User.Role.CASHIER:
            check_cashier_quota()
        user.is_active = True
        user.save()
        log_action(AuditLog.Action.UPDATE, request=request, target=user, details={"is_active": True})
        return Response(self.get_serializer(user).data)

