class ImageInvalide(Exception):
    """Image illisible ou hors des limites (nombre, taille, format) : erreur du client, jamais un echec.

    Nom et sens fixes par l'interface de la team IA (`INTEGRATION_BACKEND.md`) : un visage refuse n'est
    pas une image invalide, et une image invalide ne compte pas dans le verrouillage.
    """
