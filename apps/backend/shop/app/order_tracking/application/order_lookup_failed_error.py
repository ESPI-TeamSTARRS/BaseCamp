class OrderLookupFailedError(Exception):
    """Aucune commande ne correspond : numéro inconnu et email erroné sont indiscernables."""

    message = "Commande introuvable."
