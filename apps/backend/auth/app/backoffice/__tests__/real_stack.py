"""Outils des scenarios e2e du back-office sur la pile docker compose (aucun secret en dur).

L'operateur est cree par la commande d'exploitation `create-operator`; son gabarit facial est enrole
dans la base par le conteneur `auth` avec le FAUX verificateur de developpement; la connexion se fait
ensuite en trois temps par la passerelle, sur l'origine admin (`admin.localhost`).
"""

import base64
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[6]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
ADMIN_HOST = "admin.localhost"
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
FACE = b"\x89PNG\r\n\x1a\n" + b"visage-de-l-operateur-e2e"
OTHER_FACE = b"\x89PNG\r\n\x1a\n" + b"un-autre-visage-e2e"

# Execute dans le conteneur auth : enrole le gabarit (faux verificateur) de l'operateur.
_ENROLL = """
import base64, sys
from datetime import UTC, datetime
from sqlalchemy import create_engine, text
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import FakeReconnaissanceFaciale
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.backoffice.infrastructure.clients.face_template_key_file import load_template_cipher
from app.core.config import Settings

engine = create_engine(Settings().database_url)
with engine.connect() as connection:
    account = connection.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": sys.argv[1]}
    ).scalar_one()
template = FakeReconnaissanceFaciale().enroler([base64.b64decode(sys.argv[2])])
cipher = load_template_cipher(Settings().face_template_key_file)
with SqlAlchemyBackofficeUnitOfWork(engine, cipher) as work:
    work.templates.save(account, template, datetime.now(UTC))
    work.commit()
print("enrolled")
"""

# Execute dans un conteneur (shop ou auth) : joue des requetes JSON vers la passerelle, comme un client
# distinct (chaque conteneur a sa propre adresse). Imprime la liste [statut, corps].
_CLIENT = """
import json, sys, urllib.error, urllib.request
base, host, requests = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
results = []
for path, body in requests:
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Host": host},
    )
    try:
        response = urllib.request.urlopen(request, timeout=20)
        results.append([response.status, json.loads(response.read() or "null")])
    except urllib.error.HTTPError as error:
        results.append([error.code, json.loads(error.read() or "null")])
print(json.dumps(results))
"""


def b64(image: bytes) -> str:
    return base64.b64encode(image).decode()


def compose(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - commande fixe, arguments maitrises par le test
        ["docker", "compose", *arguments],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def create_operator(email: str, password: str = PHRASE) -> None:
    command = ["exec", "-T", "-e", f"OPERATOR_PASSWORD={password}", "auth"]
    command += ["python", "-m", "app.admin.create_operator", "--email", email]
    created = compose(*command)
    assert created.returncode == 0, created.stderr


def enroll_face(email: str, photo: bytes = FACE) -> None:
    enrolled = compose("exec", "-T", "auth", "python", "-c", _ENROLL, email, b64(photo))
    assert enrolled.returncode == 0, enrolled.stderr[-400:]


def new_operator() -> str:
    """Un operateur reel, enrole : pret pour la connexion en trois temps."""
    email = f"e2e-operator-{uuid.uuid4().hex[:10]}@example.test"
    create_operator(email)
    enroll_face(email)
    return email


def admin_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0, headers={"Host": ADMIN_HOST})


def three_steps(
    client: httpx.Client, email: str, face: bytes = FACE, password: str = PHRASE
) -> httpx.Response:
    """Identifiant, visage, mot de passe : rend la reponse du dernier temps."""
    identified = client.post("/api/auth/backoffice/identify", json={"email": email})
    assert identified.status_code == 200, identified.text
    challenge = identified.json()["challenge_id"]
    shown = client.post(
        "/api/auth/backoffice/face", json={"challenge_id": challenge, "images": [b64(face)]}
    )
    if shown.status_code != 200:
        return shown
    return client.post(
        "/api/auth/backoffice/password", json={"challenge_id": challenge, "password": password}
    )


def operator_bearer(email: str, password: str = PHRASE) -> dict[str, str]:
    """En-tete d'autorisation de l'operateur, obtenu par la vraie connexion en trois temps."""
    with admin_client() as client:
        response = three_steps(client, email, password=password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def from_container(
    service: str, requests: list[tuple[str, dict[str, Any]]], host: str = ADMIN_HOST
) -> list[list[Any]]:
    """Joue des requetes depuis le conteneur `service` vers la passerelle (adresse source propre)."""
    output = compose(
        "exec",
        "-T",
        service,
        "python",
        "-c",
        _CLIENT,
        "http://traefik:9080",
        host,
        json.dumps(requests),
    )
    assert output.returncode == 0, output.stderr[-400:]
    return list(json.loads(output.stdout.strip().splitlines()[-1]))
