class ConfirmationKeyReusedError(Exception):
    """La clé d'idempotence a déjà servi pour une autre demande de confirmation."""
