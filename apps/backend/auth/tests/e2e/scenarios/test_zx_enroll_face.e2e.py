"""Enrolement du visage d'un operateur par la commande d'exploitation `enroll-face` (WORK-63).

La commande tourne dans un conteneur `auth` a usage unique, photos montees en lecture seule : les photos
ne sont ni copiees ni ecrites. Le verificateur de la pile de developpement est le FAUX
(`APP_FACE_VERIFIER=fake`); le gabarit est chiffre au repos avec la cle du secret monte.
"""

import os
import shutil
import uuid
from pathlib import Path

import httpx
import pytest

from app.backoffice.__tests__.real_stack import (
    BASE_URL,
    FACE,
    OTHER_FACE,
    PHRASE,
    admin_client,
    compose,
    create_operator,
    enroll_face,
    operator_bearer,
    three_steps,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _photos(folder: Path) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for index, content in enumerate((FACE, PNG_HEADER + b"variante-2", PNG_HEADER + b"variante-3")):
        (folder / f"{index}.png").write_bytes(content)
        names.append(f"/photos/{index}.png")
    return names


def _enroll(email: str, folder: Path, images: list[str]) -> str:
    command = ["run", "--rm", "--no-deps", "-v", f"{folder}:/photos:ro", "auth"]
    command += ["python", "-m", "app.backoffice.enroll_face", "--email", email, "--images", *images]
    result = compose(*command)
    return (
        f"{result.returncode}|{result.stdout}|{result.stderr}"  # le bruit de compose est sur stderr
    )


@pytest.fixture
def operator() -> str:
    email = f"e2e-enroll-{uuid.uuid4().hex[:10]}@example.test"
    create_operator(email)
    return email


def test_without_a_template_the_back_office_login_is_refused(operator: str) -> None:
    with admin_client() as client:
        response = three_steps(client, operator)

    assert response.status_code == 401


def test_the_command_enrols_then_the_operator_can_log_in(operator: str, tmp_path: Path) -> None:
    outcome = _enroll(operator, tmp_path / "photos", _photos(tmp_path / "photos"))

    assert outcome.startswith("0|") and "Visage enrôlé : " in outcome
    with admin_client() as client:
        assert three_steps(client, operator).status_code == 200
    with admin_client() as client:
        assert three_steps(client, operator, face=OTHER_FACE).status_code == 401


def _psql(sql: str) -> str:
    result = compose(
        "exec",
        "-T",
        "postgres-auth",
        "sh",
        "-c",
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "{sql}"',
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_the_template_is_stored_encrypted(operator: str, tmp_path: Path) -> None:
    _enroll(operator, tmp_path / "photos", _photos(tmp_path / "photos"))
    sql = (
        "SELECT encode(substring(t.template from 1 for 1), 'hex'), length(t.template) "  # noqa: S608
        f"FROM operator_face_templates t JOIN users u ON u.id = t.account_id WHERE u.email = '{operator}'"
    )

    version, length = _psql(sql).split("|")

    assert version == "01"  # version du format chiffre
    assert int(length) == 1 + 12 + 2069 + 16  # version, nonce, gabarit, etiquette AES-GCM


def test_the_command_refuses_a_non_operator_and_a_wrong_photo_count(
    operator: str, tmp_path: Path
) -> None:
    folder = tmp_path / "photos"
    images = _photos(folder)

    unknown = _enroll("inconnu@example.test", folder, images)
    too_few = _enroll(operator, folder, images[:2])

    assert unknown.startswith("1|") and "Aucun operateur actif" in unknown
    assert too_few.startswith("1|") and "Il faut de 3 a 10 photos." in too_few


def test_disabling_an_operator_deletes_their_template(operator: str, tmp_path: Path) -> None:
    target = f"e2e-target-{uuid.uuid4().hex[:10]}@example.test"
    create_operator(target)
    _enroll(target, tmp_path / "photos", _photos(tmp_path / "photos"))
    admin = f"e2e-admin-{uuid.uuid4().hex[:10]}@example.test"
    create_operator(admin)
    enroll_face(admin)
    headers = operator_bearer(admin, PHRASE)
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        listing = site.get("/api/auth/admin/users?limit=100", headers=headers).json()["items"]
        target_id = next(item["id"] for item in listing if item["email"] == target)
        disabled = site.post(f"/api/auth/admin/users/{target_id}/disable", headers=headers)

    count = _psql(f"SELECT count(*) FROM operator_face_templates WHERE account_id = '{target_id}'")  # noqa: S608
    assert disabled.status_code == 200
    assert count == "0"
