import hashlib
import hmac

from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.domain.value_objects.face_images import (
    MAX_ENROLLMENT_PHOTOS,
    validate_face_images,
    validate_images,
)

TEMPLATE_SIZE = 2069  # taille du gabarit serialise de la team IA
DIGEST_SIZE = 32


class FakeReconnaissanceFaciale(ReconnaissanceFaciale):
    """Faux adaptateur pour les tests et le developpement : AUCUNE reconnaissance reelle.

    Le gabarit est l'empreinte SHA-256 de la premiere photo, complete a 2 069 octets; une capture est
    reconnue si c'est exactement la meme image. Il n'est charge qu'avec `APP_FACE_VERIFIER=fake` en
    developpement : jamais en production.
    """

    def enroler(self, photos: list[bytes]) -> bytes:
        images = validate_images(photos, 1, MAX_ENROLLMENT_PHOTOS)
        return hashlib.sha256(images[0]).digest().ljust(TEMPLATE_SIZE, b"\x00")

    def verifier(self, capture: bytes, gabarit: bytes) -> bool:
        if len(gabarit) != TEMPLATE_SIZE:
            raise GabaritInvalide
        try:
            validate_face_images([capture])
        except ImageInvalide:
            raise ImageInvalide from None
        return hmac.compare_digest(hashlib.sha256(capture).digest(), gabarit[:DIGEST_SIZE])
