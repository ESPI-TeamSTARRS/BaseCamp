class RefundKeyReusedError(Exception):
    """La clé d'idempotence a déjà servi pour un autre remboursement (autre montant ou intention)."""
