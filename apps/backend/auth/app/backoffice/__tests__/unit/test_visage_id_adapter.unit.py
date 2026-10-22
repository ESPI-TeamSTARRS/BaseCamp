"""L'adaptateur du package `visage-id`, teste avec un FAUX module `visage_id` (aucune reconnaissance reelle).

Le package de la team IA n'est pas necessaire ici : on verifie ce que l'adaptateur en fait (instance
unique, seuil, traduction des erreurs, aucun score exposé). La reconnaissance reelle est eprouvee par
le test de contrat sur de vraies photos (voir `test_reconnaissance_contract.integ.py`).
"""

import importlib
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide


class PackageImageInvalide(ValueError): ...


class PackageAucunVisage(ValueError): ...


class PackageGabaritInvalide(ValueError): ...


@dataclass
class Verdict:
    reconnu: bool
    score: float = (
        0.87  # le package expose un score : l'adaptateur ne doit jamais le laisser sortir
    )


class Recorder:
    instances: ClassVar[list["FakeReconnaisseur"]] = []


class FakeReconnaisseur:
    def __init__(self, seuil: float = 0.23) -> None:
        self.seuil = seuil
        self.verifications: list[tuple[object, object]] = []
        self.reconnu = True
        self.error: Exception | None = None
        Recorder.instances.append(self)

    def creer_gabarit(self, images: list[object]) -> object:
        if self.error is not None:
            raise self.error
        return ("gabarit", len(images))

    def verifier(self, image: object, gabarit: object) -> Verdict:
        if self.error is not None:
            raise self.error
        self.verifications.append((image, gabarit))
        return Verdict(self.reconnu)


def _decoder_image(octets: bytes) -> object:
    if octets == b"illisible":
        raise PackageImageInvalide("illisible")
    return ("image", octets)


def _gabarit_depuis_octets(octets: bytes) -> object:
    if octets == b"corrompu":
        raise PackageGabaritInvalide("corrompu")
    return ("gabarit", octets)


@pytest.fixture
def adapter_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.ModuleType]:
    Recorder.instances.clear()
    package = types.ModuleType("visage_id")
    package.__dict__.update(
        Reconnaisseur=FakeReconnaisseur,
        decoder_image=_decoder_image,
        gabarit_depuis_octets=_gabarit_depuis_octets,
        gabarit_en_octets=lambda gabarit: b"octets-" + repr(gabarit).encode(),
        ImageInvalide=PackageImageInvalide,
        AucunVisage=PackageAucunVisage,
        GabaritInvalide=PackageGabaritInvalide,
    )
    monkeypatch.setitem(sys.modules, "visage_id", package)
    name = "app.backoffice.infrastructure.clients.visage_id_reconnaissance"
    monkeypatch.delitem(sys.modules, name, raising=False)
    yield importlib.import_module(name)
    sys.modules.pop(name, None)


def _adapter(module: types.ModuleType, threshold: float = 0.23) -> Any:
    return module.VisageIdReconnaissance(threshold)


class TestVisageIdAdapter:
    def test_the_recognizer_is_created_once_with_the_configured_threshold(
        self, adapter_module: types.ModuleType
    ) -> None:
        adapter = _adapter(adapter_module, 0.31)

        adapter.verifier(b"a", b"g")
        adapter.verifier(b"b", b"g")
        adapter.enroler([b"1", b"2", b"3"])

        assert len(Recorder.instances) == 1
        assert Recorder.instances[0].seuil == 0.31

    def test_enrolment_gives_the_serialised_template_as_bytes(
        self, adapter_module: types.ModuleType
    ) -> None:
        template = _adapter(adapter_module).enroler([b"1", b"2", b"3"])

        assert isinstance(template, bytes)
        assert template == b"octets-('gabarit', 3)"

    @pytest.mark.parametrize("known", [True, False])
    def test_the_verdict_is_a_boolean_and_never_the_score(
        self, adapter_module: types.ModuleType, known: bool
    ) -> None:
        adapter = _adapter(adapter_module)
        Recorder.instances[0].reconnu = known

        result = adapter.verifier(b"capture", b"gabarit")

        assert result is known
        assert not isinstance(result, float)

    def test_the_capture_and_the_template_are_decoded_before_the_comparison(
        self, adapter_module: types.ModuleType
    ) -> None:
        adapter = _adapter(adapter_module)

        adapter.verifier(b"capture", b"gabarit")

        assert Recorder.instances[0].verifications == [
            (("image", b"capture"), ("gabarit", b"gabarit"))
        ]

    def test_an_unreadable_capture_is_an_invalid_image(
        self, adapter_module: types.ModuleType
    ) -> None:
        with pytest.raises(ImageInvalide):
            _adapter(adapter_module).verifier(b"illisible", b"gabarit")

    def test_a_corrupt_template_is_an_invalid_template(
        self, adapter_module: types.ModuleType
    ) -> None:
        with pytest.raises(GabaritInvalide):
            _adapter(adapter_module).verifier(b"capture", b"corrompu")

    def test_the_package_template_error_is_translated_too(
        self, adapter_module: types.ModuleType
    ) -> None:
        adapter = _adapter(adapter_module)
        Recorder.instances[0].error = PackageGabaritInvalide("autre modele")

        with pytest.raises(GabaritInvalide):
            adapter.verifier(b"capture", b"gabarit")

    def test_no_face_at_enrolment_is_its_own_error(self, adapter_module: types.ModuleType) -> None:
        adapter = _adapter(adapter_module)
        Recorder.instances[0].error = PackageAucunVisage("aucun visage")

        with pytest.raises(AucunVisage):
            adapter.enroler([b"1", b"2", b"3"])

    def test_no_face_is_still_an_invalid_image_for_callers_of_the_port(
        self, adapter_module: types.ModuleType
    ) -> None:
        adapter = _adapter(adapter_module)
        Recorder.instances[0].error = PackageAucunVisage("aucun visage")

        with pytest.raises(ImageInvalide):
            adapter.enroler([b"1", b"2", b"3"])

    def test_an_unreadable_photo_at_enrolment_is_an_invalid_image(
        self, adapter_module: types.ModuleType
    ) -> None:
        with pytest.raises(ImageInvalide):
            _adapter(adapter_module).enroler([b"1", b"illisible", b"3"])

    def test_a_package_message_never_reaches_the_translated_error(
        self, adapter_module: types.ModuleType
    ) -> None:
        with pytest.raises(ImageInvalide) as raised:
            _adapter(adapter_module).verifier(b"illisible", b"gabarit")

        assert raised.value.__cause__ is None and "illisible" not in str(raised.value)


class TestWiringWithoutThePackage:
    def test_the_service_refuses_to_start_when_the_package_is_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.backoffice.composition import build_face_recognizer
        from app.core.config import Settings

        monkeypatch.setitem(sys.modules, "visage_id", None)  # import impossible
        monkeypatch.delitem(
            sys.modules,
            "app.backoffice.infrastructure.clients.visage_id_reconnaissance",
            raising=False,
        )

        with pytest.raises(RuntimeError, match="visage-id package"):
            build_face_recognizer(Settings(face_verifier="visage-id"))

    def test_the_real_adapter_is_wired_with_the_configured_threshold(
        self, adapter_module: types.ModuleType
    ) -> None:
        from app.backoffice.composition import build_face_recognizer
        from app.core.config import Settings

        recognizer = build_face_recognizer(
            Settings(
                face_verifier="visage-id",
                face_threshold=0.4,
                environment="production",
                log_pseudonym_key="k" * 32,
            )
        )

        assert isinstance(recognizer, adapter_module.VisageIdReconnaissance)
        assert Recorder.instances[-1].seuil == 0.4
