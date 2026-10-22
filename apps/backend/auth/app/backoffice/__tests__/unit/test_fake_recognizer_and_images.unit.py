import pytest

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.value_objects.face_images import (
    MAX_IMAGE_BYTES,
    validate_face_images,
)
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    TEMPLATE_SIZE,
    FakeReconnaissanceFaciale,
)


class TestFaceImages:
    def test_one_to_three_jpeg_or_png_are_accepted(self) -> None:
        assert validate_face_images([PNG]) == (PNG,)
        assert len(validate_face_images([PNG, JPEG, OTHER_PNG])) == 3

    @pytest.mark.parametrize("count", [0, 4])
    def test_the_count_is_bounded(self, count: int) -> None:
        with pytest.raises(ImageInvalide):
            validate_face_images([PNG] * count)

    def test_the_size_is_bounded_to_one_megabyte(self) -> None:
        assert validate_face_images([PNG + b"x" * (MAX_IMAGE_BYTES - len(PNG))])
        with pytest.raises(ImageInvalide):
            validate_face_images([PNG + b"x" * (MAX_IMAGE_BYTES - len(PNG) + 1)])

    @pytest.mark.parametrize("data", [b"", b"GIF89a", b"%PDF-1.7", b"<svg/>", b"\x89PNG"])
    def test_the_format_is_checked_on_the_bytes_not_on_a_declared_type(self, data: bytes) -> None:
        with pytest.raises(ImageInvalide):
            validate_face_images([data])


class TestFakeRecognizer:
    def test_the_template_has_the_serialised_size(self) -> None:
        assert len(FakeReconnaissanceFaciale().enroler([PNG])) == TEMPLATE_SIZE == 2069

    def test_it_enrols_up_to_ten_photos_and_refuses_more(self) -> None:
        recognizer = FakeReconnaissanceFaciale()

        assert len(recognizer.enroler([PNG] * 10)) == TEMPLATE_SIZE
        with pytest.raises(ImageInvalide):
            recognizer.enroler([PNG] * 11)

    def test_the_same_image_is_recognised_and_another_is_not(self) -> None:
        recognizer = FakeReconnaissanceFaciale()
        template = recognizer.enroler([PNG])

        assert recognizer.verifier(PNG, template) is True
        assert recognizer.verifier(OTHER_PNG, template) is False

    def test_a_template_of_the_wrong_size_is_invalid(self) -> None:
        with pytest.raises(GabaritInvalide):
            FakeReconnaissanceFaciale().verifier(PNG, b"court")

    def test_an_unreadable_capture_is_an_invalid_image(self) -> None:
        recognizer = FakeReconnaissanceFaciale()

        with pytest.raises(ImageInvalide):
            recognizer.verifier(b"pas une image", recognizer.enroler([PNG]))

    def test_enrolment_refuses_an_unreadable_photo(self) -> None:
        with pytest.raises(ImageInvalide):
            FakeReconnaissanceFaciale().enroler([b"pas une image"])
