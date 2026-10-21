class ConfirmationDeliveryError(Exception):
    """L'email n'a pas pu être remis (serveur d'envoi arrêté, refus, délai dépassé)."""
