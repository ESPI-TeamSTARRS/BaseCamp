class GabaritInvalide(Exception):
    """Le gabarit stocke de l'operateur n'est pas exploitable (corrompu, mauvaise taille) : 409 et journal.

    Nom et sens fixes par l'interface de la team IA. Ce n'est pas la faute du visiteur : il ne compte
    pas comme un visage refuse.
    """
