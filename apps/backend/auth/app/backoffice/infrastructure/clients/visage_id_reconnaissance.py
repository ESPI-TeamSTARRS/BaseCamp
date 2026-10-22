"""Adaptateur du package `visage-id` de la team IA (depot ML-Reco) : le SEUL fichier qui l'importe.

Le port `ReconnaissanceFaciale` ne connait ni le package, ni ses exceptions, ni le score : le
domaine et l'application restent testables avec le faux adaptateur.
"""

from visage_id import (
    AucunVisage as PackageAucunVisage,
)
from visage_id import (
    GabaritInvalide as PackageGabaritInvalide,
)
from visage_id import (
    ImageInvalide as PackageImageInvalide,
)
from visage_id import (
    Reconnaisseur,
    decoder_image,
    gabarit_depuis_octets,
    gabarit_en_octets,
)

from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale


class VisageIdReconnaissance(ReconnaissanceFaciale):
    """Une instance pour toute la vie du processus : le `Reconnaisseur` charge les deux modeles ONNX
    (~14 Mo, embarques dans le package, aucun telechargement) et un verrou interne serialise les calculs.

    Les endpoints qui l'appellent sont synchrones (`def`, pool de threads) : ne jamais l'appeler depuis
    `async def`. Echoue des l'instanciation si les modeles manquent : le service ne demarre pas.
    """

    def __init__(self, threshold: float) -> None:
        self._recognizer = Reconnaisseur(seuil=threshold)

    def enroler(self, photos: list[bytes]) -> bytes:
        try:
            template = self._recognizer.creer_gabarit([decoder_image(photo) for photo in photos])
            return bytes(gabarit_en_octets(template))
        except PackageAucunVisage:
            raise AucunVisage from None
        except PackageImageInvalide:
            raise ImageInvalide from None

    def verifier(self, capture: bytes, gabarit: bytes) -> bool:
        """Oui ou non, jamais le score. Une capture sans visage n'est pas une erreur : `False`."""
        try:
            verdict = self._recognizer.verifier(
                decoder_image(capture), gabarit_depuis_octets(gabarit)
            )
        except PackageImageInvalide:
            raise ImageInvalide from None
        except PackageGabaritInvalide:
            raise GabaritInvalide from None
        return bool(verdict.reconnu)
