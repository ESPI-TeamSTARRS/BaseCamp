import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.backoffice.__tests__.cipher import TEST_CIPHER, TEST_KEY
from app.backoffice.__tests__.fakes import PNG
from app.backoffice.composition import build_face_recognizer
from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    TEMPLATE_SIZE,
    FakeReconnaissanceFaciale,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.core.config import Settings
from app.login.__tests__.schema import insert_user, migrated_engine
from app.main import create_app

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestStartup:
    def test_the_back_office_off_needs_no_verifier(self) -> None:
        Settings(backoffice_enabled=False, face_verifier="none")

    def test_the_back_office_on_without_a_verifier_refuses_to_start(self) -> None:
        with pytest.raises(ValueError, match="real face verifier"):
            Settings(backoffice_enabled=True, face_verifier="none")

    @pytest.mark.parametrize("environment", ["production", "staging", "prod"])
    def test_the_fake_is_refused_outside_development(self, environment: str) -> None:
        with pytest.raises(ValueError, match="only allowed in dev and local"):
            Settings(
                backoffice_enabled=True,
                face_verifier="fake",
                environment=environment,
                log_pseudonym_key="k" * 32,
            )

    @pytest.mark.parametrize("environment", ["dev", "local"])
    def test_the_fake_is_loaded_in_development(self, environment: str) -> None:
        settings = Settings(backoffice_enabled=True, face_verifier="fake", environment=environment)

        assert isinstance(build_face_recognizer(settings), FakeReconnaissanceFaciale)

    def test_without_a_real_adapter_the_wiring_itself_refuses(self) -> None:
        settings = Settings(face_verifier="none")

        with pytest.raises(RuntimeError, match="real face verifier"):
            build_face_recognizer(settings)

    def test_the_application_starts_with_the_back_office_in_development(
        self, tmp_path: Path
    ) -> None:
        key = tmp_path / "face.key"
        key.write_text(base64.b64encode(TEST_KEY).decode(), encoding="ascii")
        settings = Settings(
            backoffice_enabled=True, face_verifier="fake", face_template_key_file=str(key)
        )

        application = create_app(settings)

        assert "/backoffice/identify" in application.openapi()["paths"]

    def test_the_back_office_refuses_to_start_without_the_template_key(
        self, tmp_path: Path
    ) -> None:
        settings = Settings(
            backoffice_enabled=True,
            face_verifier="fake",
            face_template_key_file=str(tmp_path / "absente.key"),
        )

        with pytest.raises(ValueError, match="missing or unreadable"):
            create_app(settings)

    def test_the_back_office_off_needs_no_template_key(self) -> None:
        create_app(Settings(backoffice_enabled=False, face_template_key_file="/nulle/part"))


class TestChallengeStorage:
    def _challenge(self, digest: str = "d" * 64, ttl: int = 120) -> LoginChallenge:
        return LoginChallenge.issue(digest, None, "fp-mail", "fp-ip", NOW, ttl)

    def test_a_challenge_is_taken_once(self) -> None:
        engine = migrated_engine()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(self._challenge())
            work.commit()

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            first = work.challenges.take("d" * 64, NOW)
            work.commit()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            second = work.challenges.take("d" * 64, NOW)

        assert first is not None and first.email_hash == "fp-mail" and first.decoy
        assert second is None

    def test_an_expired_challenge_is_not_given_and_is_removed(self) -> None:
        engine = migrated_engine()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(self._challenge())
            work.commit()

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            taken = work.challenges.take("d" * 64, NOW + timedelta(minutes=3))
            work.commit()

        assert taken is None

    def test_re_adding_a_challenge_replaces_it_with_the_face_ok_state(self) -> None:
        engine = migrated_engine()
        challenge = self._challenge()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(challenge)
            work.commit()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(challenge.with_face_ok())
            work.commit()

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            stored = work.challenges.take("d" * 64, NOW)

        assert stored is not None and stored.face_ok

    def test_purge_removes_only_expired_challenges(self) -> None:
        engine = migrated_engine()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(self._challenge("a" * 64, ttl=10))
            work.challenges.add(self._challenge("b" * 64, ttl=600))
            work.commit()

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            purged = work.challenges.purge_expired(NOW + timedelta(minutes=1))
            work.commit()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            kept = work.challenges.take("b" * 64, NOW + timedelta(minutes=1))

        assert purged == 1 and kept is not None

    def test_a_transaction_without_commit_changes_nothing(self) -> None:
        engine = migrated_engine()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.challenges.add(self._challenge())

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            assert work.challenges.take("d" * 64, NOW) is None


class TestTemplateStorage:
    def test_a_template_is_saved_found_and_replaced(self) -> None:
        engine = migrated_engine()
        operator = uuid4()
        insert_user(engine, operator, "op@example.com", "x", "operator")
        template = FakeReconnaissanceFaciale().enroler([PNG])
        assert len(template) == TEMPLATE_SIZE
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            assert work.templates.find(operator) is None
            work.templates.save(operator, template, NOW)
            work.commit()
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.templates.save(operator, b"\x01" * TEMPLATE_SIZE, NOW)
            work.commit()

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            stored = work.templates.find(operator)

        assert stored == b"\x01" * TEMPLATE_SIZE
