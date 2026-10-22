from app.backoffice.domain.exceptions.image_invalide import ImageInvalide


class AucunVisage(ImageInvalide):
    """Aucune des photos d'enrolement ne contient de visage exploitable.

    C'est une `ImageInvalide` (erreur de la saisie, jamais un echec de connexion) que la commande
    d'enrolement distingue pour guider l'operateur.
    """
