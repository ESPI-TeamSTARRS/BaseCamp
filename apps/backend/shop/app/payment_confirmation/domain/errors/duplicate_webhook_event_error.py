class DuplicateWebhookEventError(Exception):
    """L'événement a été enregistré entre-temps par une autre requête : c'est un rejeu."""
