class VerificationKeysUnavailableError(Exception):
    """Aucune cle de verification connue et `auth` ne repond pas : le jeton ne peut pas etre juge.

    Ce n'est pas un rejet : un jeton dont la cle est en cache n'est jamais touche par une panne
    d'`auth`; sans aucune cle, `payment` repond 503 plutot que de refuser a tort.
    """
