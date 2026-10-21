class InsufficientStockError(Exception):
    """Stock devenu insuffisant : rien n'a ete reserve (transaction annulee)."""

    message = "Stock insuffisant pour un ou plusieurs articles."
