"""Reinitialisation du mot de passe sur la pile reelle : Traefik, auth, Postgres et Mailpit.

Les emails sont lus dans l'API de Mailpit (`E2E_MAILPIT_URL`) ; sans cette variable, ces scenarios
sont ignores. Chaque scenario utilise une adresse unique et supprime ses messages. Le limiteur par IP
de la passerelle (20/min, rafale de 10) peut repondre 429 : les appels sont rejoues apres une pause.
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
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
MAILPIT_URL = os.environ.get("E2E_MAILPIT_URL", "")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
NEW_PHRASE = "Bivouac-Vanoise-" + uuid.uuid4().hex[:12]
TOKEN_PATTERN = re.compile(r"/compte/reinitialiser#token=([A-Za-z0-9_-]+)")
MAIL_TIMEOUT_SECONDS = 15.0
TOO_MANY_REQUESTS = 429
GENERIC_INVALID = {"detail": "Lien de réinitialisation invalide ou expiré."}

needs_mailbox = pytest.mark.skipif(not MAILPIT_URL, reason="definir E2E_MAILPIT_URL (Mailpit)")


@dataclass(frozen=True)
class Mail:
    subject: str
    body: str


class Mailbox:
    def __init__(self) -> None:
        self._http = httpx.Client(base_url=MAILPIT_URL, timeout=5.0)

    def wait_for(self, address: str, count: int = 1, subject: str = "") -> list[Mail]:
        deadline = time.monotonic() + MAIL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            query = f"to:{address}" + (f' subject:"{subject}"' if subject else "")
            found = self._http.get("/api/v1/search", params={"query": query}).json()
            if found["messages_count"] >= count:
                return [self._read(item["ID"]) for item in found["messages"]]
            time.sleep(0.3)
        raise AssertionError(f"{count} email(s) attendu(s), delai depasse")

    def count(self, address: str, subject: str) -> int:
        query = f'to:{address} subject:"{subject}"'
        found = self._http.get("/api/v1/search", params={"query": query}).json()
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


def post(client: httpx.Client, path: str, body: dict[str, str]) -> httpx.Response:
    for _ in range(8):
        response = client.post(path, json=body)
        if response.status_code != TOO_MANY_REQUESTS:
            return response
        time.sleep(4.0)
    return response


def forgot(client: httpx.Client, email: str) -> httpx.Response:
    return post(client, "/api/auth/password/forgot", {"email": email})


def reset(client: httpx.Client, token: str, password: str = NEW_PHRASE) -> httpx.Response:
    return post(client, "/api/auth/password/reset", {"token": token, "password": password})


def register_account(client: httpx.Client, mailbox: Mailbox, email: str) -> None:
    response = post(client, "/api/auth/register", {"email": email, "password": PHRASE})
    assert response.status_code == 202
    mailbox.wait_for(email)


def reset_links(mailbox: Mailbox, email: str, count: int = 1) -> list[str]:
    mails = mailbox.wait_for(email, count=count, subject="Réinitialisez")
    tokens = []
    for mail in mails:
        match = TOKEN_PATTERN.search(mail.body)
        assert match, "le lien doit porter le jeton dans le fragment d'URL"
        tokens.append(match.group(1))
    return tokens


@needs_mailbox
class TestPasswordResetFlow:
    def test_forgot_then_reset_through_the_gateway(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)

        asked = forgot(client, address)
        [mail] = mailbox.wait_for(address, subject="Réinitialisez")
        [token] = reset_links(mailbox, address)
        done = reset(client, token)
        replay = reset(client, token, "encore-un-autre-secret-42")

        assert asked.status_code == 202
        assert address not in mail.body, "le lien ne contient aucune donnee personnelle"
        assert address.split("@")[0] not in mail.body
        assert "30 minutes" in mail.body
        assert done.status_code == 200
        [notice] = mailbox.wait_for(address, subject="modifié")
        assert "modifié" in notice.subject
        assert TOKEN_PATTERN.search(notice.body) is None
        assert (replay.status_code, replay.json()) == (400, GENERIC_INVALID)

    def test_known_and_unknown_addresses_get_an_identical_response(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)
        stranger = f"e2e-{uuid.uuid4().hex[:10]}@example.test"

        known = forgot(client, address)
        unknown = forgot(client, stranger)
        malformed = forgot(client, "pas-un-email")

        assert known.status_code == 202
        for other in (unknown, malformed):
            assert (other.status_code, other.content) == (known.status_code, known.content)
            assert other.headers["content-type"] == known.headers["content-type"]
        time.sleep(1.0)
        assert mailbox.count(stranger, "Réinitialisez") == 0
        mailbox.purge(stranger)

    def test_a_new_request_invalidates_the_previous_link(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)
        forgot(client, address)
        [first] = reset_links(mailbox, address)
        forgot(client, address)
        tokens = reset_links(mailbox, address, count=2)
        second = next(token for token in tokens if token != first)

        stale = reset(client, first)
        fresh = reset(client, second)

        assert (stale.status_code, stale.json()) == (400, GENERIC_INVALID)
        assert fresh.status_code == 200

    def test_a_weak_password_is_refused_and_the_link_stays_usable(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)
        forgot(client, address)
        [token] = reset_links(mailbox, address)

        weak = reset(client, token, "Password1234")
        short = reset(client, token, "court")
        good = reset(client, token)

        for refused in (weak, short):
            assert refused.status_code == 422
            assert "Password1234" not in refused.text
            assert token not in refused.text
            assert "Traceback" not in refused.text
        assert good.status_code == 200

    def test_unknown_token_gets_the_generic_error(self, client: httpx.Client) -> None:
        response = reset(client, "x" * 43)

        assert (response.status_code, response.json()) == (400, GENERIC_INVALID)

    def test_the_per_address_limit_keeps_the_response_and_stops_the_emails(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)

        responses = [forgot(client, address) for _ in range(5)]

        assert {(r.status_code, r.content) for r in responses} == {(202, responses[0].content)}
        reset_links(mailbox, address, count=3)
        time.sleep(1.5)
        assert mailbox.count(address, "Réinitialisez") == 3

    def test_response_time_does_not_reveal_whether_the_email_exists(
        self, client: httpx.Client, mailbox: Mailbox
    ) -> None:
        known = [f"e2e-{uuid.uuid4().hex[:10]}@example.test" for _ in range(3)]
        unknown = [f"e2e-{uuid.uuid4().hex[:10]}@example.test" for _ in range(3)]
        try:
            for email in known:
                register_account(client, mailbox, email)
            known_times = [self._timed(client, email) for email in known]
            unknown_times = [self._timed(client, email) for email in unknown]
        finally:
            for email in known + unknown:
                mailbox.purge(email)

        assert abs(statistics.median(known_times) - statistics.median(unknown_times)) < 1.0

    @staticmethod
    def _timed(client: httpx.Client, email: str) -> float:
        start = time.perf_counter()
        assert forgot(client, email).status_code == 202
        return time.perf_counter() - start

    def test_unknown_field_is_refused_without_being_reflected(
        self, client: httpx.Client, address: str
    ) -> None:
        response = post(client, "/api/auth/password/forgot", {"email": address, "role": "operator"})

        assert response.status_code == 422
        assert "operator" not in response.text


@pytest.mark.skipif(
    not (MAILPIT_URL and os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_MAILPIT_URL et E2E_CHECK_LOGS=1 (docker compose requis)",
)
class TestPasswordResetLogs:
    def test_container_logs_hold_no_password_token_or_address(
        self, client: httpx.Client, mailbox: Mailbox, address: str
    ) -> None:
        register_account(client, mailbox, address)
        forgot(client, address)
        [token] = reset_links(mailbox, address)
        phrase = "journal-" + uuid.uuid4().hex
        reset(client, token, phrase)
        reset(client, token, phrase)

        logs = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "auth", "traefik"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
            check=True,
        ).stdout

        assert "auth.password_reset_completed" in logs
        for secret in (phrase, token, address, address.split("@")[0]):
            assert secret not in logs
