class InvalidTokenError(Exception):
    """Jeton refusé (signature, expiration, émetteur, nature, audience ou scope)."""
