from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.admin.__tests__.stack import OPERATOR_EMAIL as ADMIN_EMAIL
from app.admin.__tests__.stack import OTHER_OPERATOR_EMAIL, AdminStack
from app.backoffice.__tests__.cipher import TEST_CIPHER
from app.backoffice.__tests__.fakes import PNG
from app.backoffice.__tests__.stack import BackofficeStack
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.infrastructure.clients.aes_gcm_template_cipher import AesGcmTemplateCipher
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.schema import insert_user, migrated_engine

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMPLATE = bytes(range(256)) * 8 + b"y" * 21


class TestEncryptedAtRest:
    def test_the_database_never_holds_the_template_in_clear(self) -> None:
        engine = migrated_engine()
        operator = uuid4()
        insert_user(engine, operator, "op@example.com", "x", "operator")

        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.templates.save(operator, TEMPLATE, NOW)
            work.commit()
        with engine.connect() as connection:
            raw = bytes(
                connection.execute(
                    text("SELECT template FROM operator_face_templates")
                ).scalar_one()
            )

        assert raw != TEMPLATE and TEMPLATE[:64] not in raw
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            assert work.templates.find(operator) == TEMPLATE

    def test_another_key_cannot_read_the_stored_template(self) -> None:
        engine = migrated_engine()
        operator = uuid4()
        insert_user(engine, operator, "op@example.com", "x", "operator")
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.templates.save(operator, TEMPLATE, NOW)
            work.commit()

        with (
            SqlAlchemyBackofficeUnitOfWork(engine, AesGcmTemplateCipher(b"z" * 32)) as work,
            pytest.raises(GabaritInvalide),
        ):
            work.templates.find(operator)

    def test_a_template_copied_to_another_account_row_is_refused(self) -> None:
        engine = migrated_engine()
        first, second = uuid4(), uuid4()
        insert_user(engine, first, "a@example.com", "x", "operator")
        insert_user(engine, second, "b@example.com", "x", "operator")
        with SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work:
            work.templates.save(first, TEMPLATE, NOW)
            work.commit()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO operator_face_templates SELECT :b, template, updated_at FROM operator_face_templates WHERE account_id = :a"
                ),
                {"a": first.hex, "b": second.hex},
            )

        with (
            SqlAlchemyBackofficeUnitOfWork(engine, TEST_CIPHER) as work,
            pytest.raises(GabaritInvalide),
        ):
            work.templates.find(second)


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[BackofficeStack]:
    stack = BackofficeStack(events)
    yield stack
    stack.engine.dispose()


@pytest.fixture
async def client(stack: BackofficeStack) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as http:
        yield http


class TestUnreadableStoredTemplate:
    async def test_a_tampered_template_is_a_409_logged_and_never_a_failure(
        self,
        client: AsyncClient,
        stack: BackofficeStack,
        events: InMemoryBusinessEventLogger,
    ) -> None:
        stack.exec("UPDATE operator_face_templates SET template = x'0101'")
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await stack.face(client, challenge, PNG)

        assert response.status_code == 409
        assert any(e.reason == "invalid_template" for e in events.events)
        assert stack.scalar("SELECT COUNT(*) FROM login_lockouts") == 0


class TestDisablingDeletesTheTemplate:
    @pytest.fixture
    def admin(self, events: InMemoryBusinessEventLogger) -> Iterator[AdminStack]:
        admin = AdminStack(events)
        yield admin
        admin.engine.dispose()

    async def test_a_disabled_operator_loses_their_template(self, admin: AdminStack) -> None:
        target = admin.add_account(OTHER_OPERATOR_EMAIL, role="operator")
        with admin.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO operator_face_templates VALUES (:id, x'0102', :now)"),
                {"id": target.hex, "now": NOW.isoformat(sep=" ")},
            )
        async with AsyncClient(
            transport=ASGITransport(app=admin.application), base_url="http://test"
        ) as http:
            headers = await admin.token_of(http, ADMIN_EMAIL)

            response = await http.post(f"/admin/users/{target}/disable", headers=headers)

        assert response.status_code == 200
        assert admin.scalar("SELECT COUNT(*) FROM operator_face_templates") == 0
