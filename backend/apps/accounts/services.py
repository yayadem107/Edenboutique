from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def revoke_all_tokens(user):
    """Déconnecte l'utilisateur de tous ses appareils (tokens de rafraîchissement révoqués)."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
