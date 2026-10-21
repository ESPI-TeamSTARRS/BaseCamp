import secrets

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
_LENGTH = 10


class OrderNumberGenerator:
    """Numero de commande lisible, non sequentiel (ne revele pas le volume de ventes)."""

    @staticmethod
    def generate() -> str:
        return "BC-" + "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
