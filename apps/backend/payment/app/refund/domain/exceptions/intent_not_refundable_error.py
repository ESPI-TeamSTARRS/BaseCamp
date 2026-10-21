class IntentNotRefundableError(Exception):
    """L'intention n'a pas été encaissée (en attente, échouée, annulée ou expirée)."""
