class IdempotencyKeyReusedError(Exception):
    """La cle d'idempotence a deja servi pour une commande de contenu different."""

    message = "Cette cle d'idempotence est deja utilisee pour une autre commande."
