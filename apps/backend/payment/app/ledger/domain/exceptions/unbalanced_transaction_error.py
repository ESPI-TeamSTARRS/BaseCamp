class UnbalancedTransactionError(Exception):
    """Les débits d'une transaction ne sont pas égaux à ses crédits (ou elle est incomplète)."""
