from pathlib import Path

import pytest

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.__tests__.flow import OPERATOR_EMAIL, Flow
from app.backoffice.application.enroll_operator_face import EnrollOperatorFaceUseCase
from app.backoffice.application.enrollment_errors import EnrollmentRefusedError
from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.enroll_face import read_photos, run
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    TEMPLATE_SIZE,
    FakeReconnaissanceFaciale,
)
from app.login.__tests__.fakes import FakeEmailFingerprinter

PHOTOS = [PNG, JPEG, OTHER_PNG]


def _use_case(
    flow: Flow, recognizer: FakeReconnaissanceFaciale | None = None
) -> EnrollOperatorFaceUseCase:
    from app.backoffice.__tests__.fakes import FakeBackofficeUnitOfWork
    from app.login.__tests__.fakes import FakeUnitOfWork

    return EnrollOperatorFaceUseCase(
        lambda: FakeUnitOfWork(flow.accounts),
        lambda: FakeBackofficeUnitOfWork(flow.store),
        recognizer or flow.recognizer,
        FakeEmailFingerprinter(),
        flow.clock,
        flow.events,
    )


class TestEnrollment:
    def test_three_to_ten_photos_store_a_template_for_the_operator(self) -> None:
        flow = Flow()
        flow.store.templates.clear()

        account_id = _use_case(flow).execute(OPERATOR_EMAIL, PHOTOS)

        assert account_id == flow.operator.id
        assert len(flow.store.templates[flow.operator.id]) == TEMPLATE_SIZE
        (event,) = flow.events.events
        assert event.event == "auth.backoffice_face_enrolled"
        assert event.attributes["photos"] == 3

    def test_the_operator_can_then_pass_the_face_step(self) -> None:
        flow = Flow()
        flow.store.templates.clear()
        _use_case(flow).execute(OPERATOR_EMAIL, PHOTOS)
        challenge = flow.identify.execute(OPERATOR_EMAIL, "203.0.113.9").challenge_id

        flow.face.execute(challenge, [PNG], "203.0.113.9")

        assert next(iter(flow.store.challenges.values())).face_ok

    def test_without_a_template_the_login_is_refused(self) -> None:
        from app.backoffice.application.backoffice_errors import BackofficeRefusedError

        flow = Flow()
        flow.store.templates.clear()
        challenge = flow.identify.execute(OPERATOR_EMAIL, "203.0.113.9").challenge_id

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [PNG], "203.0.113.9")

    def test_enrolling_again_replaces_the_template(self) -> None:
        flow = Flow()
        first = flow.store.templates[flow.operator.id]

        _use_case(flow).execute(OPERATOR_EMAIL, [OTHER_PNG, JPEG, PNG])

        assert flow.store.templates[flow.operator.id] != first

    @pytest.mark.parametrize("count", [0, 1, 2, 11])
    def test_the_photo_count_is_bounded(self, count: int) -> None:
        flow = Flow()

        with pytest.raises(EnrollmentRefusedError) as raised:
            _use_case(flow).execute(OPERATOR_EMAIL, [PNG] * count)

        assert raised.value.code == "photo_count"

    @pytest.mark.parametrize("email", ["inconnu@example.com", "client@example.com"])
    def test_only_an_active_operator_can_be_enrolled(self, email: str) -> None:
        flow = Flow()

        with pytest.raises(EnrollmentRefusedError) as raised:
            _use_case(flow).execute(email, PHOTOS)

        assert raised.value.code == "unknown_operator"
        assert email not in repr(flow.events.events)

    def test_a_disabled_operator_is_refused(self) -> None:
        flow = Flow()
        flow.accounts.accounts[flow.operator.id] = type(flow.operator)(
            flow.operator.id,
            flow.operator.email,
            flow.operator.password_hash,
            "operator",
            True,
            True,
        )

        with pytest.raises(EnrollmentRefusedError):
            _use_case(flow).execute(OPERATOR_EMAIL, PHOTOS)

    @pytest.mark.parametrize(
        "photo",
        [b"", b"GIF89a-pas-une-image", PNG + b"x" * 1_048_577],
        ids=["vide", "gif", "plus-d-un-mo"],
    )
    def test_a_photo_that_is_not_a_small_jpeg_or_png_is_refused(self, photo: bytes) -> None:
        flow = Flow()

        with pytest.raises(EnrollmentRefusedError) as raised:
            _use_case(flow).execute(OPERATOR_EMAIL, [PNG, PNG, photo])

        assert raised.value.code == "invalid_photo"

    def test_a_photo_without_a_face_is_a_distinct_refusal(self) -> None:
        class NoFace(FakeReconnaissanceFaciale):
            def enroler(self, photos: list[bytes]) -> bytes:
                raise AucunVisage

        flow = Flow()

        with pytest.raises(EnrollmentRefusedError) as raised:
            _use_case(flow, NoFace()).execute(OPERATOR_EMAIL, PHOTOS)

        assert raised.value.code == "no_face"

    def test_an_unreadable_photo_for_the_recognizer_is_refused(self) -> None:
        class Unreadable(FakeReconnaissanceFaciale):
            def enroler(self, photos: list[bytes]) -> bytes:
                raise ImageInvalide

        flow = Flow()

        with pytest.raises(EnrollmentRefusedError) as raised:
            _use_case(flow, Unreadable()).execute(OPERATOR_EMAIL, PHOTOS)

        assert raised.value.code == "invalid_photo"

    def test_no_photo_template_or_email_reaches_the_events(self) -> None:
        flow = Flow()
        _use_case(flow).execute(OPERATOR_EMAIL, PHOTOS)
        with pytest.raises(EnrollmentRefusedError):
            _use_case(flow).execute("inconnu@example.com", PHOTOS)

        text = repr(flow.events.events)

        assert "PNG" not in text and OPERATOR_EMAIL not in text and "inconnu@" not in text


class TestCommand:
    def _photos(self, tmp_path: Path, count: int = 3) -> list[str]:
        paths = []
        for index in range(count):
            path = tmp_path / f"photo{index}.png"
            path.write_bytes(PNG + bytes([index]))
            paths.append(str(path))
        return paths

    def test_it_enrols_and_prints_the_account_without_biometric_data(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = Flow()
        flow.store.templates.clear()

        code = run(_use_case(flow), OPERATOR_EMAIL, self._photos(tmp_path))

        out = capsys.readouterr()
        assert code == 0
        assert str(flow.operator.id) in out.out and out.err == ""
        assert "PNG" not in out.out

    def test_it_exits_1_with_a_fixed_message_when_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = Flow()

        code = run(_use_case(flow), "inconnu@example.com", self._photos(tmp_path))

        err = capsys.readouterr().err
        assert code == 1
        assert err.strip() == "Aucun operateur actif avec cette adresse."

    def test_a_missing_file_is_an_input_error_that_does_not_echo_the_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = Flow()
        missing = str(tmp_path / "secret-name.png")

        code = run(_use_case(flow), OPERATOR_EMAIL, [missing])

        assert code == 1
        assert "secret-name" not in capsys.readouterr().err

    def test_photos_are_read_in_memory_only_and_a_huge_file_is_refused(
        self, tmp_path: Path
    ) -> None:
        huge = tmp_path / "huge.png"
        huge.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024 + 1))

        with pytest.raises(ValueError, match="volumineuse"):
            read_photos([str(huge)])
        before = sorted(p.name for p in tmp_path.iterdir())
        assert sorted(p.name for p in tmp_path.iterdir()) == before  # aucune copie ecrite
