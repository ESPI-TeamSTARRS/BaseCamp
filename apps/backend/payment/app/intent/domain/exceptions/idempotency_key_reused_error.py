class IdempotencyKeyReusedError(Exception):
    """La clé d'idempotence a déjà servi avec un corps de demande différent."""
