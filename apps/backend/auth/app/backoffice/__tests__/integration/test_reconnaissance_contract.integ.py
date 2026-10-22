"""Test de contrat du port `ReconnaissanceFaciale`, passe par le faux ET par l'adaptateur reel.

Le faux tourne toujours. L'adaptateur reel (`visage-id`, team IA) ne tourne que si le package est
installe ET si `FACE_CONTRACT_PHOTOS` designe un dossier de vraies photos de coequipiers consentants
(jamais dans le depot) :

  <dossier>/personne_a/1.jpg ... (au moins 4 photos de la personne A)
  <dossier>/personne_b/1.jpg ... (au moins 1 photo d'une autre personne)

Sans ces photos, le cas reel est ignore avec un message explicite (aucune reconnaissance n'est inventee).
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    TEMPLATE_SIZE,
    FakeReconnaissanceFaciale,
)

PHOTOS_ENV = "FACE_CONTRACT_PHOTOS"
GARBAGE = b"ceci n'est pas une image"


@dataclass(frozen=True)
class Samples:
    """Photos du contrat : 3 d'enrolement, 1 de la meme personne, 1 d'une autre personne."""

    enrolment: list[bytes]
    same_person: bytes
    other_person: bytes


def _fake_samples() -> Samples:
    return Samples([PNG, JPEG, OTHER_PNG], PNG, b"\x89PNG\r\n\x1a\nune-autre-personne")


def _real_samples() -> Samples:
    folder = Path(os.environ[PHOTOS_ENV])
    a = sorted((folder / "personne_a").glob("*"))
    b = sorted((folder / "personne_b").glob("*"))
    assert len(a) >= 4 and len(b) >= 1, "il faut 4 photos de A et 1 de B"
    return Samples([p.read_bytes() for p in a[:3]], a[3].read_bytes(), b[0].read_bytes())


@pytest.fixture(params=["fake", "visage-id"])
def contract(request: pytest.FixtureRequest) -> Iterator[tuple[ReconnaissanceFaciale, Samples]]:
    if request.param == "fake":
        yield FakeReconnaissanceFaciale(), _fake_samples()
        return
    if not os.environ.get(PHOTOS_ENV):
        pytest.skip(f"definir {PHOTOS_ENV} (dossier de vraies photos hors depot) pour le cas reel")
    pytest.importorskip("visage_id", reason="package visage-id non installe")
    from app.backoffice.infrastructure.clients.visage_id_reconnaissance import (
        VisageIdReconnaissance,
    )

    yield VisageIdReconnaissance(0.23), _real_samples()


class TestReconnaissanceContract:
    def test_enrolment_gives_a_serialised_template_of_the_documented_size(
        self, contract: tuple[ReconnaissanceFaciale, Samples]
    ) -> None:
        recognizer, samples = contract

        template = recognizer.enroler(samples.enrolment)

        assert isinstance(template, bytes)
        assert len(template) == TEMPLATE_SIZE == 2069

    def test_the_same_person_is_recognised_with_a_plain_boolean(
        self, contract: tuple[ReconnaissanceFaciale, Samples]
    ) -> None:
        recognizer, samples = contract
        template = recognizer.enroler(samples.enrolment)

        verdict = recognizer.verifier(samples.same_person, template)

        assert verdict is True

    def test_another_person_is_refused_with_a_plain_boolean(
        self, contract: tuple[ReconnaissanceFaciale, Samples]
    ) -> None:
        recognizer, samples = contract
        template = recognizer.enroler(samples.enrolment)

        verdict = recognizer.verifier(samples.other_person, template)

        assert verdict is False

    def test_an_unreadable_capture_is_an_invalid_image(
        self, contract: tuple[ReconnaissanceFaciale, Samples]
    ) -> None:
        recognizer, samples = contract
        template = recognizer.enroler(samples.enrolment)

        with pytest.raises(ImageInvalide):
            recognizer.verifier(GARBAGE, template)

    def test_an_unreadable_enrolment_photo_is_an_invalid_image(
        self, contract: tuple[ReconnaissanceFaciale, Samples]
    ) -> None:
        recognizer, samples = contract

        with pytest.raises(ImageInvalide):
            recognizer.enroler([*samples.enrolment[:2], GARBAGE])

    @pytest.mark.parametrize("template", [b"", b"trop court", b"\x00" * 10])
    def test_a_corrupt_template_is_an_invalid_template(
        self, contract: tuple[ReconnaissanceFaciale, Samples], template: bytes
    ) -> None:
        recognizer, samples = contract

        with pytest.raises(GabaritInvalide):
            recognizer.verifier(samples.same_person, template)
