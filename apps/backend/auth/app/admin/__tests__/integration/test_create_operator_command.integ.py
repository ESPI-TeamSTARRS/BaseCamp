import getpass
import io
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin import create_operator
from app.admin.__tests__.stack import AdminStack
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger

STRONG = "Bivouac-au-sommet-2026"


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[AdminStack]:
    stack = AdminStack(events)
    yield stack
    stack.engine.dispose()


def run(
    stack: AdminStack,
    events: InMemoryBusinessEventLogger,
    email: str,
    environ: dict[str, str],
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = create_operator.run(stack.engine, events, email, environ)
    return code, out.getvalue(), err.getvalue()


class TestCreateOperatorCommand:
    async def test_it_creates_an_operator_who_cannot_administer_with_the_classic_login(
        self, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        code, out, err = run(stack, events, "nouveau@example.com", {"OPERATOR_PASSWORD": STRONG})

        assert (code, err) == (0, "")
        assert out.startswith("Opérateur créé : ")
        assert (
            stack.scalar("SELECT role FROM users WHERE email = 'nouveau@example.com'") == "operator"
        )
        assert (
            stack.scalar(
                "SELECT email_verified_at IS NOT NULL FROM users WHERE email = 'nouveau@example.com'"
            )
            == 1
        )
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            login = await client.post(
                "/login", json={"email": "nouveau@example.com", "password": STRONG}
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            # Le login classique ne delivre plus `operator` : l'administration exige la connexion
            # en trois temps (WORK-59).
            assert (await client.get("/admin/users", headers=headers)).status_code == 403

    def test_the_password_is_hashed_in_argon2id_and_never_printed_or_logged(
        self, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        _, out, err = run(stack, events, "nouveau@example.com", {"OPERATOR_PASSWORD": STRONG})

        stored = stack.scalar("SELECT password_hash FROM users WHERE email = 'nouveau@example.com'")
        assert str(stored).startswith("$argon2id$")
        assert STRONG not in out + err + repr(events.events) + str(stored)

    def test_a_weak_password_is_refused_with_a_fixed_message(
        self, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        code, out, err = run(stack, events, "nouveau@example.com", {"OPERATOR_PASSWORD": "court"})

        assert code == 1
        assert "12 caractères" in err
        assert "court" not in out + repr(events.events)
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE email = 'nouveau@example.com'") == 0

    def test_an_existing_address_and_an_invalid_one_are_refused(
        self, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        taken = run(stack, events, "camille@example.com", {"OPERATOR_PASSWORD": STRONG})
        invalid = run(stack, events, "pas-une-adresse", {"OPERATOR_PASSWORD": STRONG})

        assert taken[0] == invalid[0] == 1
        assert "existe déjà" in taken[2]
        assert "invalide" in invalid[2]
        assert (
            stack.scalar("SELECT role FROM users WHERE email = 'camille@example.com'") == "customer"
        )

    def test_without_the_variable_the_password_is_typed_twice_without_echo(
        self,
        stack: AdminStack,
        events: InMemoryBusinessEventLogger,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        answers = iter([STRONG, STRONG])
        monkeypatch.setattr(getpass, "getpass", lambda prompt: next(answers))

        code, _, _ = run(stack, events, "tape@example.com", {})

        assert code == 0

    def test_two_different_typed_passwords_are_refused(
        self,
        stack: AdminStack,
        events: InMemoryBusinessEventLogger,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        answers = iter([STRONG, STRONG + "x"])
        monkeypatch.setattr(getpass, "getpass", lambda prompt: next(answers))

        code, _, err = run(stack, events, "tape@example.com", {})

        assert code == 1
        assert "different" in err
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE email = 'tape@example.com'") == 0


class TestPublicRegistrationNeverElevates:
    async def test_the_role_in_the_body_is_refused_and_never_stored(
        self, stack: AdminStack
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            response = await client.post(
                "/register",
                json={"email": "pirate@example.com", "password": STRONG, "role": "operator"},
            )

        assert response.status_code == 422
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE email = 'pirate@example.com'") == 0
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE role = 'operator'") == 1


class TestMain:
    def test_main_reads_the_settings_and_returns_the_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, stack: AdminStack
    ) -> None:
        monkeypatch.setattr(create_operator, "create_engine", lambda *a, **k: stack.engine)
        monkeypatch.setenv("OPERATOR_PASSWORD", STRONG)
        monkeypatch.setenv("APP_ENVIRONMENT", "dev")

        code = create_operator.main(["--email", "cli@example.com"])

        assert code == 0
        assert stack.scalar("SELECT role FROM users WHERE email = 'cli@example.com'") == "operator"
