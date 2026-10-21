class InvalidClientCredentialsError(Exception):
    """Client inconnu, secret invalide, scope ou audience refusés : une seule erreur, sans cause."""
