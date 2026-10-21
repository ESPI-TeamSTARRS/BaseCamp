class PaymentUnavailableError(Exception):
    """Le service de paiement ne répond pas (arrêt, délai, surcharge) : réessayer plus tard.

    Aucun détail technique (hôte, jeton, corps) n'est conservé dans l'exception.
    """
