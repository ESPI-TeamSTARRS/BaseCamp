"""Parcours complet du back-office sur la pile réelle (WORK-64) : connexion, catalogue, commandes, refus, blocage.

Tout passe par la passerelle, sur l'hôte du back-office, comme un navigateur : les routes serveur du back-office
(`/session/*`, `/bff/*`) relaient vers `auth` et `shop`. Le visage accepté s'appuie sur le FAUX vérificateur
de développement (`APP_FACE_VERIFIER=fake`) avec la même image à l'enrôlement et à la connexion : la pile
e2e n'embarque pas le modèle de `visage-id` ni de photos de personnes, et le dépôt ne doit en contenir aucune.
Ce qui est vérifié ici est tout le reste de la chaîne (jetons, double facteur, verrouillage, journaux,
métriques); la reconnaissance réelle est couverte par les tests de l'adaptateur `visage-id` d'`auth`.

Le scénario clôt aussi la contrainte transverse : les événements des trois services respectent le schéma
commun, aucun secret ni donnée personnelle n'est journalisé, `/metrics` d'`auth` compte les tentatives par
étape et résultat et les blocages, sans aucune étiquette contenant l'e-mail. Il s'exécute après les
scénarios de verrouillage (nom en `zz`) : une connexion réussie remet à zéro le compteur de l'adresse source.
"""

import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

from app.backoffice.__tests__.real_stack import (
    ADMIN_HOST,
    BASE_URL,
    FACE,
    OTHER_FACE,
    PHRASE,
    REPO_ROOT,
    b64,
    compose,
    new_operator,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
SCHEMA = REPO_ROOT / "docs/development/log-event.schema.json"
ADMIN = {"Host": ADMIN_HOST}
SAME_ORIGIN = {**ADMIN, "Sec-Fetch-Site": "same-origin"}
GENERIC = {"detail": "Identifiants invalides."}
WRONG_PASSWORD = "pas-le-bon-mot-de-passe-journey"
FILTER = "filtre-a-eau-portable"
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /api/shop/orders à 10/min
RATE_LIMIT_ATTEMPTS = 8
FIVE_MINUTES = (290, 300)

# Exécuté DANS le conteneur auth : secondes restantes du verrou d'une étape pour un sujet.
_LOCK_STATUS = """
import json, sys
from datetime import UTC, datetime
from sqlalchemy import create_engine
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.composition import build_lockout_service

class Silent(BusinessEventLogger):
    def log(self, event):
        pass

settings = Settings()
service = build_lockout_service(settings, create_engine(settings.database_url), Silent())
status = service.check(sys.argv[1], sys.argv[2], datetime.now(UTC))
print(json.dumps([status.locked, status.retry_after_seconds]))
"""

SCRAPE = (
    "import urllib.request;"
    "print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"
)


@dataclass
class Journey:
    """Ce que les scénarios ont manipulé : le dernier test vérifie qu'aucun n'a fui dans les journaux."""

    secrets: list[str] = field(default_factory=list)
    order: dict[str, Any] = field(default_factory=dict)
    viewed_order_id: str = ""
    baseline: dict[str, float] = field(default_factory=dict)


def _scrape() -> str:
    output = compose("exec", "-T", "auth", "python", "-c", SCRAPE)
    assert output.returncode == 0, output.stderr[-400:]
    return output.stdout


def _counters(body: str) -> dict[str, float]:
    """Séries du back-office de `/metrics`, par nom et étiquettes."""
    series: dict[str, float] = {}
    for line in body.splitlines():
        if line.startswith("auth_backoffice_"):
            name, _, value = line.rpartition(" ")
            series[name] = float(value)
    return series


def _delta(after: dict[str, float], before: dict[str, float], series: str) -> float:
    return after.get(series, 0.0) - before.get(series, 0.0)


@pytest.fixture(scope="module")
def journey() -> Journey:
    return Journey(baseline=_counters(_scrape()))


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=False) as session:
        yield session


def _step(client: httpx.Client, step: str, body: dict[str, Any]) -> httpx.Response:
    return client.post(f"/session/{step}", json=body, headers=SAME_ORIGIN)


def _login(
    client: httpx.Client, email: str, face: bytes = FACE, password: str = PHRASE
) -> httpx.Response:
    """Les trois temps par le back-office ; rend la réponse de la dernière étape atteinte."""
    identified = _step(client, "identify", {"email": email})
    assert identified.status_code == 200, identified.text
    challenge = identified.json()["challenge_id"]
    shown = _step(client, "face", {"challenge_id": challenge, "images": [b64(face)]})
    if shown.status_code != 200:
        return shown
    return _step(client, "password", {"challenge_id": challenge, "password": password})


def _cookie(response: httpx.Response) -> str:
    for line in response.headers.get_list("set-cookie"):
        name, _, rest = line.partition("=")
        if name.strip() == "bo_access":
            return rest.split(";", 1)[0]
    raise AssertionError("pas de cookie de session")


def _bff(client: httpx.Client, path: str, token: str) -> httpx.Response:
    return client.get(path, headers={**SAME_ORIGIN, "Cookie": f"bo_access={token}"})


def _place_order(email: str) -> dict[str, Any]:
    """Une commande passée sur le site client (domaine principal), par un invité."""
    body = {
        "email": email,
        "shippingAddress": {
            "fullName": "Client Parcours E2E",
            "line1": "7 rue du Parcours",
            "postalCode": "75002",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": FILTER, "quantity": 1}],
    }
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
        for _ in range(RATE_LIMIT_ATTEMPTS):
            response = site.post(
                "/api/shop/orders",
                json=body,
                headers={"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"},
            )
            if response.status_code != 429:
                break
            time.sleep(RATE_LIMIT_PAUSE_SECONDS)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _service_logs(service: str) -> list[dict[str, Any]]:
    logs = compose("logs", service, "--no-color", "--tail", "5000", timeout=120).stdout
    events: list[dict[str, Any]] = []
    for line in logs.splitlines():
        if "{" not in line:
            continue
        try:
            events.append(json.loads(line[line.index("{") :]))
        except json.JSONDecodeError:
            continue
    return events


def _lock_status(step: str, email_hash: str) -> list[Any]:
    output = compose("exec", "-T", "auth", "python", "-c", _LOCK_STATUS, step, email_hash)
    assert output.returncode == 0, output.stderr[-400:]
    return list(json.loads(output.stdout.strip().splitlines()[-1]))


class TestCompleteJourney:
    def test_login_catalog_orders_and_logout(self, client: httpx.Client, journey: Journey) -> None:
        email = new_operator()
        journey.secrets += [email, PHRASE]

        login = _login(client, email)

        assert login.status_code == 200 and login.json() == {"ok": True}
        token = _cookie(login)
        journey.secrets.append(token)
        assert token not in login.text
        # Écran protégé servi avec la session, catalogue lu par les routes serveur.
        assert (
            client.get("/commandes", headers={**ADMIN, "Cookie": f"bo_access={token}"}).status_code
            == 200
        )
        catalog = _bff(client, "/bff/products?limit=5", token)
        assert catalog.status_code == 200 and catalog.json()["total"] > 0

        # Commande passée sur le site client, retrouvée dans le back-office avec le bon statut.
        customer_email = f"e2e.parcours.{uuid.uuid4().hex[:10]}@example.org"
        journey.secrets.append(customer_email)
        journey.order = _place_order(customer_email)
        listed = _bff(client, f"/bff/orders?q={journey.order['number']}", token)
        assert listed.status_code == 200
        (found,) = listed.json()["items"]
        assert (found["id"], found["status"]) == (journey.order["id"], "pending_payment")
        detail = _bff(client, f"/bff/orders/{journey.order['id']}", token)
        assert detail.status_code == 200
        body = detail.json()
        assert body["number"] == journey.order["number"] and body["email"] == customer_email
        assert body["shipping_address"]["line1"] == "7 rue du Parcours"
        journey.viewed_order_id = body["id"]

        # Déconnexion : le cookie est effacé et les écrans se referment.
        out = client.post(
            "/session/logout", headers={**SAME_ORIGIN, "Cookie": f"bo_access={token}"}
        )
        assert out.status_code == 303
        assert client.get("/commandes", headers=ADMIN).status_code == 307
        assert _bff(client, "/bff/orders", "").status_code == 401

    def test_a_wrong_face_and_a_wrong_password_are_refused_with_the_same_generic_401(
        self, client: httpx.Client, journey: Journey
    ) -> None:
        email = new_operator()
        journey.secrets += [email, WRONG_PASSWORD]

        wrong_face = _login(client, email, face=OTHER_FACE)
        wrong_password = _login(client, email, password=WRONG_PASSWORD)

        for response in (wrong_face, wrong_password):
            assert (response.status_code, response.json()) == (401, GENERIC)
            assert response.headers.get_list("set-cookie") == []

    def test_the_back_office_routes_refuse_a_token_without_the_face_factor(
        self, client: httpx.Client
    ) -> None:
        email = new_operator()
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
            classic = site.post("/api/auth/login", json={"email": email, "password": PHRASE})
        token = classic.json()["access_token"]  # connexion classique : ni operator ni amr

        assert (
            client.get("/commandes", headers={**ADMIN, "Cookie": f"bo_access={token}"}).status_code
            == 307
        )
        assert _bff(client, "/bff/orders", token).status_code == 401

    def test_three_wrong_passwords_block_the_operator_for_five_minutes(
        self, client: httpx.Client, journey: Journey
    ) -> None:
        email = new_operator()
        journey.secrets.append(email)

        for _ in range(3):
            assert _login(client, email, password=WRONG_PASSWORD).status_code == 401
        blocked = _login(client, email)  # le bon mot de passe ne passe plus : étape verrouillée

        assert (blocked.status_code, blocked.json()) == (401, GENERIC)
        assert blocked.headers.get_list("set-cookie") == []
        locked = next(
            event
            for event in reversed(_service_logs("auth"))
            if event["event"] == "auth.backoffice_lockout"
        )
        assert locked["attributes"]["step"] == "operator_password"
        status = _lock_status("operator_password", locked["attributes"]["email_hash"])
        assert status[0] is True and FIVE_MINUTES[0] <= int(status[1]) <= FIVE_MINUTES[1]


class TestSignals:
    def test_metrics_count_attempts_by_step_and_result_and_lockouts_without_any_email(
        self, journey: Journey
    ) -> None:
        body = _scrape()
        after = _counters(body)
        before = journey.baseline

        def attempts(step: str, result: str) -> float:
            return _delta(
                after, before, f'auth_backoffice_attempts_total{{step="{step}",result="{result}"}}'
            )

        assert attempts("identify", "success") >= 5
        assert attempts("face", "success") >= 4
        assert attempts("face", "denied") >= 1
        assert attempts("password", "success") >= 1
        assert attempts("password", "denied") >= 4
        assert (
            _delta(after, before, 'auth_backoffice_lockouts_total{step="operator_password"}') >= 1
        )
        series = [line for line in body.splitlines() if line.startswith("auth_backoffice_")]
        assert series
        assert not any("@" in line or "email" in line for line in series)
        assert "example.test" not in body and "example.org" not in body

    def test_events_of_the_three_services_follow_the_common_schema(self) -> None:
        validator = Draft202012Validator(json.loads(Path(SCHEMA).read_text(encoding="utf-8")))
        seen: dict[str, set[str]] = {}

        for service, prefix in (
            ("backoffice", "backoffice."),
            ("auth", "auth.backoffice_"),
            ("shop", "admin_orders."),
        ):
            events = [
                e for e in _service_logs(service) if str(e.get("event", "")).startswith(prefix)
            ]
            assert events, f"aucun événement {prefix} dans les journaux de {service}"
            for event in events:
                errors = sorted(validator.iter_errors(event), key=str)
                assert not errors, f"{service} : {event.get('event')} : {errors[0].message}"
            seen[service] = {str(e["event"]) for e in events}

        assert {
            "backoffice.login_identify",
            "backoffice.login_face",
            "backoffice.login_password",
            "backoffice.logout",
            "backoffice.order_view",
        } <= seen["backoffice"]
        assert {"auth.backoffice_face_result", "auth.backoffice_lockout"} <= seen["auth"]
        assert "admin_orders.viewed" in seen["shop"]

    def test_the_order_view_audit_names_the_operator_and_the_order_without_personal_data(
        self, journey: Journey
    ) -> None:
        events = [
            e for e in _service_logs("backoffice") if e.get("event") == "backoffice.order_view"
        ]

        viewed = [e for e in events if e.get("resource_id") == journey.viewed_order_id]

        assert viewed, "aucune consultation de détail journalisée"
        for event in viewed:
            assert event["outcome"] == "success" and event["resource_type"] == "order"
            assert event["actor_type"] == "user" and re.fullmatch(
                r"[0-9a-f]{16}", event["actor_id"]
            )

    def test_no_secret_nor_personal_data_reaches_any_log(self, journey: Journey) -> None:
        logs = "".join(
            compose("logs", service, "--no-color", "--tail", "5000", timeout=120).stdout
            for service in ("backoffice", "auth", "shop")
        )

        assert journey.secrets
        for secret in journey.secrets:
            assert secret not in logs, "une valeur sensible est apparue dans les journaux"
        assert "7 rue du Parcours" not in logs and "Client Parcours E2E" not in logs
        # Les journaux contiennent bien les événements (le test ne passe pas à vide).
        assert "backoffice.order_view" in logs
