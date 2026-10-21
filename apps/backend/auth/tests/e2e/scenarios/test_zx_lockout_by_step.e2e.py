"""Verrouillage par étape et par adresse source sur la pile réelle (WORK-56).

Aucune route ne porte encore ces étapes (la connexion en trois temps les consommera) : on exerce le
vrai `LockoutService` branché sur le vrai Postgres, depuis le conteneur `auth` (`docker compose exec`).
Le redémarrage du conteneur prouve que les verrous sont en base, pas en mémoire.
"""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]
pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="définir E2E_CHECK_LOGS=1 (docker compose requis)",
)

# Exécuté DANS le conteneur auth : usage `<action> <sujet>` ; imprime un JSON.
SCRIPT = """
import json, sys
from datetime import UTC, datetime
from sqlalchemy import create_engine
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.composition import build_lockout_service
from app.lockout.domain.entities.lockout_subject import LockoutSubject
from app.lockout.domain.enums.subject_type import SubjectType

class Silent(BusinessEventLogger):
    def log(self, event):
        pass

settings = Settings()
service = build_lockout_service(settings, create_engine(settings.database_url), Silent())
action, subject = sys.argv[1], sys.argv[2]
now = datetime.now(UTC)
account, address = SubjectType.ACCOUNT, SubjectType.SOURCE_ADDRESS
if action == "fail":
    step, kind, times = sys.argv[3], sys.argv[4], int(sys.argv[5])
    for _ in range(times):
        status = service.record_failure(step, subject, datetime.now(UTC), SubjectType(kind))
    print(json.dumps({"locked": status.locked, "seconds": status.retry_after_seconds}))
elif action == "check":
    result = {}
    for step in ("operator_password", "face", "password"):
        status = service.check(step, subject, now)
        result[step] = [status.locked, status.retry_after_seconds]
    status = service.check("face", subject, now, address)
    result["face@address"] = [status.locked, status.retry_after_seconds]
    print(json.dumps(result))
elif action == "clear":
    service.clear([
        LockoutSubject("operator_password", subject),
        LockoutSubject("face", subject),
        LockoutSubject("face", subject, address),
    ])
    print(json.dumps({"cleared": True}))
"""


def _auth(*arguments: str) -> dict[str, object]:
    command = ["docker", "compose", "exec", "-T", "auth", "python", "-c", SCRIPT, *arguments]
    completed = subprocess.run(  # noqa: S603 - commande fixe, arguments maîtrisés par le test
        command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=True
    )
    return dict(json.loads(completed.stdout.strip().splitlines()[-1]))


def _fail(subject: str, step: str, kind: str, times: int) -> dict[str, object]:
    return _auth("fail", subject, step, kind, str(times))


@pytest.fixture
def subject() -> str:
    return f"e2e-{uuid.uuid4().hex[:16]}"


def test_each_step_has_its_own_threshold_and_counter(subject: str) -> None:
    assert _fail(subject, "operator_password", "account", 2)["locked"] is False
    assert _fail(subject, "face", "account", 4)["locked"] is False

    password = _fail(subject, "operator_password", "account", 1)
    face = _fail(subject, "face", "account", 1)

    assert password == {"locked": True, "seconds": password["seconds"]}
    assert 290 <= int(str(password["seconds"])) <= 300  # 5 minutes fixes
    assert face["locked"] is True
    # un client ordinaire (étape password, règle progressive) n'est pas concerné
    assert _auth("check", subject)["password"] == [False, 0]


def test_a_source_address_has_its_own_counter(subject: str) -> None:
    assert _fail(subject, "face", "address", 19)["locked"] is False

    assert _fail(subject, "face", "address", 1)["locked"] is True
    checked = _auth("check", subject)
    assert checked["face@address"][0] is True  # type: ignore[index]
    assert checked["face"] == [False, 0]  # le compteur du compte est resté libre


def test_locks_survive_a_restart_and_a_complete_login_clears_them(subject: str) -> None:
    _fail(subject, "operator_password", "account", 3)
    subprocess.run(
        ["docker", "compose", "restart", "auth"],  # noqa: S607
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=180,
    )
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "90", "auth"],  # noqa: S607
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=180,
    )

    assert _auth("check", subject)["operator_password"][0] is True  # type: ignore[index]

    _auth("clear", subject)

    assert _auth("check", subject)["operator_password"] == [False, 0]
