"""Invitation d'un operateur par lien a usage unique, sur la pile reelle (WORK-67) : Traefik, auth, Postgres.

Le lien est genere par la commande d'exploitation `create-operator-invite` (dans le conteneur `auth`, comme
le ferait un administrateur IT sur la VM), puis consomme par la passerelle sur l'origine admin. Le
verificateur de la pile de developpement est le FAUX (`APP_FACE_VERIFIER=fake`).
"""

import os
import re
import shutil
import uuid

import httpx
import jwt
import pytest

from app.backoffice.__tests__.real_stack import (
    BASE_URL,
    FACE,
    PHRASE,
    admin_client,
    b64,
    compose,
    from_container,
    three_steps,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
PATH = "/api/auth/backoffice/invitation/complete"
GENERIC = {"detail": "Invitation invalide ou expirée."}
PNG_HEADER = b"\x89PNG\r\n\x1a\n"
MIB = 1024 * 1024


def _photos(count: int = 3, size: int = 0) -> list[bytes]:
    photos = [FACE] + [PNG_HEADER + f"variante-{index}".encode() for index in range(count - 1)]
    if size:
        photos = [photo + b"\0" * (size - len(photo)) for photo in photos]
    return photos


def _body(
    token: str, password: str = PHRASE, photos: list[bytes] | None = None
) -> dict[str, object]:
    return {
        "token": token,
        "password": password,
        "images": [b64(photo) for photo in (photos or _photos())],
    }


def _invite(email: str) -> str:
    result = compose(
        "exec",
        "-T",
        "auth",
        "python",
        "-m",
        "app.backoffice.create_operator_invite",
        "--email",
        email,
    )
    assert result.returncode == 0, result.stderr[-400:]
    assert (
        result.stdout.count("#token=") == 1
    )  # le lien n'apparait qu'une fois (jamais dans les journaux)
    found = re.search(r"https?://admin\.[^\s]+/invitation#token=([A-Za-z0-9_-]+)", result.stdout)
    assert found, "lien d'invitation absent de la sortie"
    return found.group(1)


@pytest.fixture
def email() -> str:
    return f"e2e-invite-{uuid.uuid4().hex[:10]}@example.test"


@pytest.fixture
def client() -> httpx.Client:
    return admin_client()


def test_the_invited_operator_creates_the_account_then_logs_in_in_three_steps(
    client: httpx.Client, email: str
) -> None:
    token = _invite(email)

    created = client.post(PATH, json=_body(token))

    assert created.status_code == 201, created.text
    assert created.json() == {"created": True}
    assert created.headers["cache-control"] == "no-store"
    login = three_steps(client, email)
    assert login.status_code == 200, login.text
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    assert claims["roles"] == ["operator"] and claims["amr"] == ["face", "pwd"]


def test_a_used_link_cannot_be_used_again(client: httpx.Client, email: str) -> None:
    token = _invite(email)
    assert client.post(PATH, json=_body(token)).status_code == 201

    again = client.post(PATH, json=_body(token, password="Autre-" + uuid.uuid4().hex))

    assert (again.status_code, again.json()) == (401, GENERIC)


def test_unknown_and_used_tokens_get_the_same_answer(client: httpx.Client, email: str) -> None:
    token = _invite(email)
    client.post(PATH, json=_body(token))

    used = client.post(PATH, json=_body(token))
    unknown = client.post(PATH, json=_body(uuid.uuid4().hex * 2))

    assert (
        (used.status_code, used.json()) == (unknown.status_code, unknown.json()) == (401, GENERIC)
    )


def test_a_revoked_link_is_refused(client: httpx.Client, email: str) -> None:
    token = _invite(email)

    revoked = compose(
        "exec",
        "-T",
        "auth",
        "python",
        "-m",
        "app.backoffice.revoke_operator_invite",
        "--email",
        email,
    )

    assert revoked.returncode == 0 and "1 invitation(s) révoquée(s)." in revoked.stdout
    assert token not in revoked.stdout
    response = client.post(PATH, json=_body(token))
    assert (response.status_code, response.json()) == (401, GENERIC)


def test_a_weak_password_or_too_few_photos_keep_the_link_usable(
    client: httpx.Client, email: str
) -> None:
    token = _invite(email)

    weak = client.post(PATH, json=_body(token, password="court"))
    few = client.post(PATH, json=_body(token, photos=_photos(2)))
    bad_image = client.post(PATH, json=_body(token, photos=[FACE, FACE, b"GIF89a-x"]))

    assert (weak.status_code, few.status_code, bad_image.status_code) == (422, 422, 422)
    assert client.post(PATH, json=_body(token)).status_code == 201  # le jeton n'a pas ete consomme


def test_the_route_does_not_exist_on_the_main_domain(email: str) -> None:
    token = _invite(email)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        response = site.post(PATH, json=_body(token))

    assert response.status_code == 404
    assert "created" not in response.text
    with (
        admin_client() as client
    ):  # le lien reste valable : la tentative sur le domaine principal ne l'a pas consomme
        assert client.post(PATH, json=_body(token)).status_code == 201


def test_ten_photos_of_one_megabyte_pass_the_gateway_and_an_oversized_body_is_a_413(
    client: httpx.Client, email: str
) -> None:
    token = _invite(email)

    big = client.post(PATH, json=_body(token, photos=_photos(10, size=MIB)))
    oversized = client.post(
        PATH, content=b"x" * (16 * MIB), headers={"content-type": "application/json"}
    )

    assert big.status_code == 201, big.text[:200]
    assert oversized.status_code == 413


def test_repeated_bad_tokens_lock_the_source_address_even_for_a_good_link(email: str) -> None:
    token = _invite(email)
    guesses = [(PATH, _body(f"faux-{index}-{uuid.uuid4().hex}")) for index in range(5)]

    refused = from_container("auth", guesses)
    blocked = from_container("auth", [(PATH, _body(token))])

    assert [status for status, _ in refused] == [401] * 5
    assert blocked[0][0] == 401  # l'adresse est bloquee : meme le bon lien est refuse depuis elle
    with admin_client() as other:  # une autre adresse n'est pas touchee
        assert other.post(PATH, json=_body(token)).status_code == 201


def test_neither_the_token_nor_the_password_nor_the_address_reach_the_logs(
    client: httpx.Client, email: str
) -> None:
    token = _invite(email)
    client.post(PATH, json=_body(token))

    logs = compose("logs", "--no-color", "auth", "traefik", timeout=120).stdout

    assert "auth.operator_invite_consumed" in logs
    assert token not in logs and PHRASE not in logs and email not in logs
