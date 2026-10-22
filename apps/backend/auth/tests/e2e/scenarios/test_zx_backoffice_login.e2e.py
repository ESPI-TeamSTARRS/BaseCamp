"""Connexion du back-office en trois temps sur la pile reelle (WORK-59) : Traefik, auth, Postgres.

La connexion se fait par la passerelle sur l'origine admin (`admin.localhost`). L'operateur est cree par
`create-operator` et son gabarit facial est enrole avec le FAUX verificateur de developpement
(`APP_FACE_VERIFIER=fake`, uniquement en developpement : aucune reconnaissance reelle).

Deux clients distincts (deux conteneurs, donc deux adresses sources) prouvent que le compteur par adresse
lit la vraie adresse du client derriere Traefik, pas celle du proxy. Il suppose
`AUTH_LOCKOUT_ADDRESS_MAX_FAILURES` abaisse (5 en CI) : au seuil par defaut (20), le debit de la
passerelle (30 requetes/min) empeche de le franchir en un temps raisonnable.
"""

import base64
import os
import shutil
import uuid

import httpx
import jwt
import pytest

from app.backoffice.__tests__.real_stack import (
    BASE_URL,
    FACE,
    OTHER_FACE,
    PHRASE,
    admin_client,
    b64,
    from_container,
    new_operator,
    three_steps,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
GENERIC = {"detail": "Identifiants invalides."}
ADDRESS_THRESHOLD = int(os.environ.get("AUTH_LOCKOUT_ADDRESS_MAX_FAILURES", "20"))


@pytest.fixture
def operator() -> str:
    return new_operator()


@pytest.fixture
def client() -> httpx.Client:
    return admin_client()


def _claims(token: str) -> dict[str, object]:
    return dict(jwt.decode(token, options={"verify_signature": False}))


def test_the_three_steps_give_an_operator_token_with_amr(
    client: httpx.Client, operator: str
) -> None:
    response = three_steps(client, operator)

    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    claims = _claims(token)
    assert claims["roles"] == ["operator"]
    assert claims["amr"] == ["face", "pwd"]
    assert claims["token_use"] == "client"
    assert "set-cookie" not in response.headers
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        me = site.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["roles"] == ["operator"]


def test_the_classic_login_never_gives_the_operator_role(operator: str) -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        login = site.post("/api/auth/login", json={"email": operator, "password": PHRASE})
    assert login.status_code == 200

    claims = _claims(login.json()["access_token"])

    assert claims["roles"] == []
    assert "amr" not in claims


def test_a_wrong_face_a_missing_face_and_a_replay_all_get_the_same_401(
    client: httpx.Client, operator: str
) -> None:
    wrong_face = three_steps(client, operator, face=OTHER_FACE)
    challenge = client.post("/api/auth/backoffice/identify", json={"email": operator}).json()[
        "challenge_id"
    ]
    password_only = client.post(
        "/api/auth/backoffice/password", json={"challenge_id": challenge, "password": PHRASE}
    )
    replay = client.post(
        "/api/auth/backoffice/face", json={"challenge_id": challenge, "images": [b64(FACE)]}
    )

    for response in (wrong_face, password_only, replay):
        assert (response.status_code, response.json()) == (401, GENERIC)


def test_an_unknown_identifier_is_indistinguishable_at_identify(
    client: httpx.Client, operator: str
) -> None:
    known = client.post("/api/auth/backoffice/identify", json={"email": operator})
    unknown = client.post(
        "/api/auth/backoffice/identify", json={"email": f"inconnu-{uuid.uuid4().hex[:8]}@x.test"}
    )

    assert known.status_code == unknown.status_code == 200
    assert set(known.json()) == set(unknown.json())
    assert known.json()["expires_in"] == unknown.json()["expires_in"] == 120


def test_invalid_images_are_a_422_and_never_a_failure(client: httpx.Client, operator: str) -> None:
    challenge = client.post("/api/auth/backoffice/identify", json={"email": operator}).json()[
        "challenge_id"
    ]
    bad = client.post(
        "/api/auth/backoffice/face",
        json={"challenge_id": challenge, "images": [base64.b64encode(b"GIF89a-x").decode()]},
    )
    good = client.post(
        "/api/auth/backoffice/face", json={"challenge_id": challenge, "images": [b64(FACE)]}
    )

    assert bad.status_code == 422
    assert good.status_code == 200  # le defi a survecu : ce n'etait pas un echec


def test_the_back_office_does_not_exist_on_the_main_domain(operator: str) -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        response = site.post("/api/auth/backoffice/identify", json={"email": operator})

    assert response.status_code == 404
    assert "challenge_id" not in response.text


def _face_from(service: str, email: str) -> int:
    """Identifiant puis visage CORRECT depuis le conteneur `service` ; rend le statut du visage."""
    (identify,) = from_container(service, [("/api/auth/backoffice/identify", {"email": email})])
    assert identify[0] == 200
    body = {"challenge_id": identify[1]["challenge_id"], "images": [b64(FACE)]}
    (face,) = from_container(service, [("/api/auth/backoffice/face", body)])
    return int(face[0])


def test_two_clients_behind_the_gateway_have_two_separate_address_counters(
    operator: str,
) -> None:
    if ADDRESS_THRESHOLD > 8:
        pytest.skip("abaisser AUTH_LOCKOUT_ADDRESS_MAX_FAILURES (5 en CI) pour ce scenario")
    # Le client A (conteneur shop) accumule des refus sous des identifiants inconnus : chaque compte
    # n'en voit qu'un, seul le compteur d'ADRESSE grimpe.
    for _ in range(ADDRESS_THRESHOLD):
        assert _face_from("shop", f"inconnu-{uuid.uuid4().hex[:8]}@x.test") == 401

    # A est bloque meme avec le bon operateur et le bon visage; B (autre adresse source) passe :
    # la passerelle transmet bien l'adresse de chaque client, pas celle du proxy.
    assert _face_from("shop", operator) == 401
    assert _face_from("auth", operator) == 200
