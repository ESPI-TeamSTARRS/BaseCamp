"""Parcours d'inscription d'un opérateur invité (WORK-68), sur la pile réelle : Traefik, back-office, auth.

Ce que le navigateur fait : ouvre `/invitation#token=...` sur l'origine admin (page publique, sans session),
envoie les photos et le mot de passe à la route d'auth par la passerelle, puis se connecte par les routes
serveur du back-office. La caméra et le fragment de l'adresse sont couverts par les tests de composants.
"""

import os
import re
import shutil
import uuid

import httpx
import pytest

from app.backoffice.__tests__.real_stack import (
    ADMIN_HOST,
    BASE_URL,
    FACE,
    PHRASE,
    b64,
    compose,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
ADMIN = {"Host": ADMIN_HOST}
SAME_ORIGIN = {**ADMIN, "Sec-Fetch-Site": "same-origin"}
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


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
    found = re.search(r"/(invitation)#token=([A-Za-z0-9_-]+)", result.stdout)
    assert found, "lien d'invitation absent de la sortie"
    return found.group(2)


def test_invited_operator_signs_up_then_logs_in_through_the_back_office() -> None:
    email = f"e2e-signup-{uuid.uuid4().hex[:10]}@example.test"
    token = _invite(email)
    photos = [FACE] + [PNG_HEADER + f"variante-{index}".encode() for index in range(4)]
    with httpx.Client(base_url=BASE_URL, timeout=30.0, headers=ADMIN) as browser:
        page = browser.get("/invitation", follow_redirects=False)  # le fragment n'est jamais envoyé
        created = browser.post(
            "/api/auth/backoffice/invitation/complete",
            json={"token": token, "password": PHRASE, "images": [b64(photo) for photo in photos]},
        )
        identified = browser.post("/session/identify", json={"email": email}, headers=SAME_ORIGIN)
        challenge = identified.json()["challenge_id"]
        face = browser.post(
            "/session/face",
            json={"challenge_id": challenge, "images": [b64(FACE)]},
            headers=SAME_ORIGIN,
        )
        login = browser.post(
            "/session/password",
            json={"challenge_id": challenge, "password": PHRASE},
            headers=SAME_ORIGIN,
        )

    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "noindex" in page.headers["x-robots-tag"]
    assert "camera=(self)" in page.headers["permissions-policy"]
    assert created.status_code == 201, created.text
    assert face.status_code == 200, face.text
    assert login.status_code == 200 and login.json() == {"ok": True}


def test_the_signup_page_does_not_exist_on_the_main_domain() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        response = site.get("/invitation", follow_redirects=False)

    assert response.status_code == 404
