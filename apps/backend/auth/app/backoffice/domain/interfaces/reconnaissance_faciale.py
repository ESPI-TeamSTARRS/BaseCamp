from abc import ABC, abstractmethod


class ReconnaissanceFaciale(ABC):
    """Port de la reconnaissance faciale (interface de la team IA, depot ML-Reco).

    Le score n'est jamais expose : `verifier` repond oui ou non. Les images sont traitees en memoire
    seulement, jamais ecrites sur disque ni journalisees.
    """

    @abstractmethod
    def enroler(self, photos: list[bytes]) -> bytes:
        """Gabarit serialise (2 069 octets) calcule a partir de photos du visage.

        Leve `ImageInvalide` si une photo est illisible.
        """

    @abstractmethod
    def verifier(self, capture: bytes, gabarit: bytes) -> bool:
        """Vrai si la capture est le visage du gabarit.

        Leve `ImageInvalide` si la capture est illisible, `GabaritInvalide` si le gabarit l'est.
        """
