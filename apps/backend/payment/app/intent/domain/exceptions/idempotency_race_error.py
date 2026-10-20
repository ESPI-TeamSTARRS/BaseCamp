class IdempotencyRaceError(Exception):
    """Une demande concurrente a enregistré la même clé d'idempotence."""
