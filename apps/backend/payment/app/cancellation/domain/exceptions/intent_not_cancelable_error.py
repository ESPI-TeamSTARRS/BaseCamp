class IntentNotCancelableError(Exception):
    """L'intention ne peut plus être annulée (déjà traitée, expirée ou échéance dépassée)."""
