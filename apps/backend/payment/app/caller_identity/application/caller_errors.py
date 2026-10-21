class CallerUnauthorizedError(Exception):
    """Jeton absent, invalide, expire, falsifie ou d'une autre audience : un seul 401."""


class CallerForbiddenError(Exception):
    """Jeton authentique mais sans le scope ou le role exige par la route : un seul 403."""


class IdentityUnavailableError(Exception):
    """Cles de verification illisibles et aucune en cache : 503, a reessayer."""
