"""Parcours d'inscription sur la pile reelle : Traefik, auth, Postgres et Mailpit.

Les emails sont lus dans l'API de Mailpit (`E2E_MAILPIT_URL`, publiee par docker-compose.e2e.yml) ;
sans cette variable, les scenarios qui lisent la boite mail sont ignores. Chaque scenario utilise une
adresse unique et supprime ses messages ; les comptes restent dans la base jetable de la pile.
"""

import os
import re
import shutil
import statistics
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
MAILPIT_URL = os.environ.get("E2E_MAILPIT_URL", "")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
TOKEN_PATTERN = re.compile(r"/compte/verification#token=([A-Za-z0-9_-]+)")
MAIL_TIMEOUT_SECONDS = 15.0

needs_mailbox = pytest.mark.skipif(not MAILPIT_URL, reason="definir E2E_MAILPIT_URL (Mailpit)")


@dataclass(frozen=True)
class Mail:
    subject: str
    body: str


class Mailbox:
    def __init__(self) -> None:
        self._http = httpx.Client(base_url=MAILPIT_URL, timeout=5.0)

    def wait_for(self, address: str, count: int = 1) -> list[Mail]:
        deadline = time.monotonic() + MAIL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            found = self._http.get("/api/v1/search", params={"query": f"to:{address}"}).json()
            if found["messages_count"] >= count:
                return [self._read(item["ID"]) for item in found["messages"]]
            time.sleep(0.3)
        raise AssertionError(f"{count} email(s) attendu(s), delai depasse")

    def count(self, address: str) -> int:
        found = self._http.get("/api/v1/search", params={"query": f"to:{address}"}).json()
        return int(found["messages_count"])

    def purge(self, address: str) -> None:
        self._http.delete("/api/v1/search", params={"query": f"to:{address}"})

    def _read(self, message_id: str) -> Mail:
        message = self._http.get(f"/api/v1/message/{message_id}").json()
        return Mail(subject=message["Subject"], body=message["Text"])


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        yield http


@pytest.fixture
def mailbox() -> Iterator[Mailbox]:
    yield Mailbox()


@pytest.fixture
def address(mailbox: Mailbox) -> Iterator[str]:
    value = f"e2e-{uuid.uuid4().hex[:10]}@example.test"
    yield value
    if MAILPIT_URL:
        mailbox.purge(value)


def register(client: httpx.Client, email: str, phrase: str = PHRASE) -> httpx.Response:
    return client.post("/api/auth/register", json={"email": email, "password": phrase})


def token_from(mail: Mail) -> str:
    match = TOKEN_PATTERN.search(mail.body)
    assert match, "le lien de verification doit porter le jeton dans le fragment d'URL"
    return match.group(1)


@needs_mailbox
class TestRegistrationFlow:
    def test_register_then_verify_email_through_the_gateway(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        response = register(client, address)
        [mail] = mailbox.wait_for(address)
        token = token_from(mail)

        verified = client.post("/api/auth/verify-email", json={"token": token})
        replay = client.post("/api/auth/verify-email", json={"token": token})

        assert response.status_code == 202
        assert "Confirmez" in mail.subject
        assert verified.status_code == 200
        assert replay.status_code == 400

    def test_existing_email_gets_an_identical_response_and_the_owner_is_warned(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        first = register(client, address)
        mailbox.wait_for(address)

        second = register(client, address.upper(), "une-autre-phrase-secrete-42")

        mails = mailbox.wait_for(address, count=2)
        warning = next(mail for mail in mails if "existe déjà" in mail.subject)
        assert (second.status_code, second.content) == (first.status_code, first.content)
        assert TOKEN_PATTERN.search(warning.body) is None
        assert sum(1 for mail in mails if TOKEN_PATTERN.search(mail.body)) == 1

    def test_response_time_does_not_reveal_whether_the_email_exists(
        self, client: httpx.Client, mailbox: Mailbox
    ) -> None:
        addresses = [f"e2e-{uuid.uuid4().hex[:10]}@example.test" for _ in range(2)]
        try:
            new_times = [self._timed(client, email) for email in addresses]
            known_times = [self._timed(client, email) for email in addresses]
        finally:
            for email in addresses:
                mailbox.purge(email)

        assert abs(statistics.mean(new_times) - statistics.mean(known_times)) < 0.75

    @staticmethod
    def _timed(client: httpx.Client, email: str) -> float:
        start = time.perf_counter()
        assert register(client, email).status_code == 202
        return time.perf_counter() - start

    @pytest.mark.parametrize(
        ("email", "phrase"),
        [
            ("pas-un-email", PHRASE),
            ("{address}", "court"),
            ("{address}", "Password1234"),
        ],
    )
    def test_invalid_input_is_a_sanitized_422_and_sends_no_email(
        self, client: httpx.Client, mailbox: Mailbox, address: str, email: str, phrase: str
    ) -> None:
        response = register(client, email.format(address=address), phrase)

        assert response.status_code == 422
        assert "pas-un-email" not in response.text
        assert phrase not in response.text
        assert "Traceback" not in response.text
        time.sleep(0.5)
        assert mailbox.count(address) == 0

    def test_unknown_field_is_refused_without_being_reflected(
        self, client: httpx.Client, address: str
    ) -> None:
        response = client.post(
            "/api/auth/register",
            json={"email": address, "password": PHRASE, "role": "operator"},
        )

        assert response.status_code == 422
        assert "operator" not in response.text

    def test_unknown_verification_token_gets_the_generic_error(self, client: httpx.Client) -> None:
        response = client.post("/api/auth/verify-email", json={"token": "x" * 43})

        assert response.status_code == 400
        assert response.json() == {"detail": "Lien de vérification invalide ou expiré."}

    def test_the_mailbox_is_not_exposed_by_the_gateway(self, client: httpx.Client) -> None:
        for path in ("/mailpit", "/api/v1/messages", "/api/auth/api/v1/messages", "/readyz"):
            response = client.get(path)
            assert response.status_code == 404
            assert "Mailpit" not in response.text


@pytest.mark.skipif(
    not (MAILPIT_URL and os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_MAILPIT_URL et E2E_CHECK_LOGS=1 (docker compose requis)",
)
class TestRegistrationLogs:
    def test_container_logs_hold_no_password_token_or_address(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        phrase = "journal-" + uuid.uuid4().hex
        register(client, address, phrase)
        token = token_from(mailbox.wait_for(address)[0])
        client.post("/api/auth/verify-email", json={"token": token})
        register(client, address, phrase)

        logs = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "auth", "traefik"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout

        assert logs.strip(), "les journaux de la pile doivent etre lisibles"
        for secret in (phrase, token, address, address.split("@")[0]):
            assert secret not in logs
