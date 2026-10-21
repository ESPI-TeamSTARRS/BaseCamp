class PaymentOrderNotFoundError(Exception):
    """Commande inconnue : message fixe, l'identifiant demandé n'est jamais reflété."""

    message = "Commande introuvable."
