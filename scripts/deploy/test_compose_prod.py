"""Garde-fous de la pile de production (deploy/docker-compose.prod.yml).

Ces tests ne lancent aucun conteneur : ils verifient les invariants du fichier, pour qu'une
modification ne puisse pas rouvrir un port, reintroduire un build ou une image par tag flottant.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
DYNAMIC_PROD = ROOT / "deploy" / "traefik" / "dynamic.prod.yml"
DYNAMIC_DEV = ROOT / "infra" / "traefik" / "dynamic.yml"

FIRST_PARTY_IMAGE_VARS = {"FRONT_IMAGE", "SHOP_IMAGE", "PAYMENT_IMAGE", "AUTH_IMAGE"}
# Noms de routeurs deja pris par l'ancienne pile de la VM : ne jamais les reutiliser.
RESERVED_ROUTERS = {"basecamp", "basecamp-http"}
RATE_LIMITERS = {
    "orders-rate-limit",
    "auth-signup-rate-limit",
    "auth-password-rate-limit",
    "admin-rate-limit",
    "backoffice-login-rate-limit",
}  # cle IP differente en prod

SAMPLE_ENV = {
    "FRONT_IMAGE": "ghcr.io/o/basecamp-frontend@sha256:" + "a" * 64,
    "SHOP_IMAGE": "ghcr.io/o/basecamp-shop@sha256:" + "b" * 64,
    "PAYMENT_IMAGE": "ghcr.io/o/basecamp-payment@sha256:" + "c" * 64,
    "AUTH_IMAGE": "ghcr.io/o/basecamp-auth@sha256:" + "d" * 64,
    "BASECAMP_DOMAIN": "basecamp.example.test",
    "POSTGRES_ADMIN_PASSWORD": "x",
    "SHOP_DB_PASSWORD": "x",
    "PAYMENT_DB_PASSWORD": "x",
    "AUTH_DB_PASSWORD": "x",
    "AUTH_SERVICE_CLIENT_SECRET_SHOP": "x",
    "PAYMENT_WEBHOOK_SECRET": "x",
    "LOG_PSEUDONYM_KEY": "x",
    "S3_ACCESS_KEY": "x",
    "S3_SECRET_KEY": "x",
}


def _env(**overrides: str) -> dict:
    """Environnement du processus (le CLI docker en a besoin) sans les variables de la pile."""
    base = {k: v for k, v in os.environ.items() if k not in SAMPLE_ENV}
    return {**base, **overrides}


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_aucun_build_ni_port_publie(compose: dict) -> None:
    for name, service in compose["services"].items():
        assert "build" not in service, f"{name} : pas de build en production"
        assert "ports" not in service, f"{name} : aucun port publie sur l'hote"


def test_images_applicatives_par_variable_digest(compose: dict) -> None:
    used = set()
    for service in compose["services"].values():
        image = service["image"]
        if image.startswith("${"):
            used.add(image[2:].split(":")[0].rstrip("}"))
    assert used == FIRST_PARTY_IMAGE_VARS


def test_images_tierces_epinglees_par_digest(compose: dict) -> None:
    for name, service in compose["services"].items():
        image = service["image"]
        if image.startswith("${"):
            continue
        assert "@sha256:" in image, f"{name} : image tierce sans digest ({image})"
        assert ":latest" not in image, f"{name} : tag latest interdit"


def test_limite_de_memoire_sur_chaque_service(compose: dict) -> None:
    for name, service in compose["services"].items():
        assert "mem_limit" in service, f"{name} : mem_limit manquante (VM partagee)"


def test_traefik_interne_sur_le_reseau_web_sans_collision(compose: dict) -> None:
    traefik = compose["services"]["traefik"]
    assert "web" in traefik["networks"]
    assert compose["networks"]["web"]["external"] is True
    routers = {
        key.split(".")[3] for key in traefik["labels"] if key.startswith("traefik.http.routers.")
    }
    assert routers == {"basecamp-gw", "basecamp-gw-http"}
    assert not routers & RESERVED_ROUTERS


def test_reseaux_de_donnees_restent_internes(compose: dict) -> None:
    for name in ("app", "data", "payment-net", "payment-data", "auth-data"):
        assert compose["networks"][name]["internal"] is True


def test_routage_identique_au_developpement() -> None:
    prod = yaml.safe_load(DYNAMIC_PROD.read_text(encoding="utf-8"))["http"]
    dev = yaml.safe_load(DYNAMIC_DEV.read_text(encoding="utf-8"))["http"]
    assert prod["routers"] == dev["routers"]
    assert prod["serversTransports"] == dev["serversTransports"]
    assert prod.get("services") == dev.get("services")
    prod_middlewares = {k: v for k, v in prod["middlewares"].items() if k not in RATE_LIMITERS}
    dev_middlewares = {k: v for k, v in dev["middlewares"].items() if k not in RATE_LIMITERS}
    assert prod_middlewares == dev_middlewares


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker absent")
def test_compose_config_valide_avec_un_environnement_minimal() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config", "-q"],
        env=_env(**SAMPLE_ENV),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker absent")
def test_compose_refuse_une_image_sans_reference() -> None:
    env = {k: v for k, v in SAMPLE_ENV.items() if k != "SHOP_IMAGE"}
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config", "-q"],
        env=_env(**env),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "SHOP_IMAGE" in result.stderr or "reference par digest" in result.stderr


def test_exposition_de_la_passerelle_pilotable(compose: dict) -> None:
    """GATEWAY_EXPOSE=false permet de tester la pile avant la bascule sans la router."""
    assert "GATEWAY_EXPOSE" in compose["services"]["traefik"]["labels"]["traefik.enable"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker absent")
def test_compose_rend_traefik_enable_false() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
        env=_env(**SAMPLE_ENV, GATEWAY_EXPOSE="false"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    labels = json.loads(result.stdout)["services"]["traefik"]["labels"]
    assert labels["traefik.enable"] == "false"

def test_webhook_de_paiement_recu_par_shop_seulement_et_jamais_route_par_la_passerelle(
    compose: dict,
) -> None:
    environment = compose["services"]["shop"]["environment"]
    assert environment["APP_PAYMENT_WEBHOOK_SECRET"].startswith("${PAYMENT_WEBHOOK_SECRET:?")
    for autre in ("shop-migrate", "payment", "front"):
        assert "APP_PAYMENT_WEBHOOK_SECRET" not in compose["services"][autre].get("environment", {})
    for chemin in (DYNAMIC_PROD, DYNAMIC_DEV):
        routeurs = yaml.safe_load(chemin.read_text(encoding="utf-8"))["http"]["routers"]
        assert "!PathPrefix(`/api/shop/webhooks`)" in routeurs["shop"]["rule"], chemin.name

def test_administration_du_catalogue_seulement_sur_l_origine_admin(compose: dict) -> None:
    environment = compose["services"]["shop"]["environment"]
    assert environment["APP_S3_ACCESS_KEY"].startswith("${S3_ACCESS_KEY:?")
    assert environment["APP_S3_SECRET_KEY"].startswith("${S3_SECRET_KEY:?")
    for chemin in (DYNAMIC_PROD, DYNAMIC_DEV):
        http = yaml.safe_load(chemin.read_text(encoding="utf-8"))["http"]
        admin = http["routers"]["shop-admin"]
        assert admin["rule"].startswith("HostRegexp("), chemin.name
        assert "PathPrefix(`/api/shop/admin`)" in admin["rule"]
        assert "admin-rate-limit" in admin["middlewares"]
        assert "!PathPrefix(`/api/shop/admin`)" in http["routers"]["shop"]["rule"]
        limite = http["middlewares"]["admin-body-limit"]["buffering"]["maxRequestBodyBytes"]
        assert 2 * 1024 * 1024 < limite <= 4 * 1024 * 1024
    labels = compose["services"]["traefik"]["labels"]
    assert "Host(`admin.${BASECAMP_DOMAIN}`)" in labels["traefik.http.routers.basecamp-gw.rule"]

def test_transport_des_mails_de_shop_configurable_sans_secret_dans_le_depot(compose: dict) -> None:
    environment = compose["services"]["shop"]["environment"]
    assert environment["APP_MAIL_TRANSPORT"] == "${MAIL_TRANSPORT:-smtp}"
    assert environment["APP_N8N_MAIL_URL"] == "${N8N_MAIL_URL:-}"
    assert environment["APP_N8N_MAIL_SECRET"] == "${N8N_MAIL_SECRET:-}"
    exemple = (ROOT / "deploy" / "prod.env.example").read_text(encoding="utf-8")
    assert "N8N_MAIL_SECRET=" in exemple
    for ligne in exemple.splitlines():
        if ligne.lstrip("# ").startswith("N8N_MAIL_SECRET="):
            assert ligne.split("=", 1)[1].strip() == "", "le secret n'a jamais de valeur dans le depot"


def test_connexion_backoffice_seulement_sur_l_origine_admin(compose: dict) -> None:
    for chemin in (DYNAMIC_PROD, DYNAMIC_DEV):
        http = yaml.safe_load(chemin.read_text(encoding="utf-8"))["http"]
        routeur = http["routers"]["auth-backoffice"]
        assert routeur["rule"].startswith("HostRegexp("), chemin.name
        assert "PathPrefix(`/api/auth/backoffice`)" in routeur["rule"]
        assert "!PathPrefix(`/api/auth/backoffice`)" in http["routers"]["auth"]["rule"]
        assert routeur["middlewares"][0] == "backoffice-login-rate-limit"
        limite = http["middlewares"]["backoffice-body-limit"]["buffering"]["maxRequestBodyBytes"]
        assert 4 * 1024 * 1024 < limite <= 8 * 1024 * 1024  # 3 images de 1 Mo en base64
    # La production garde le limiteur strict (le developpement est large pour les scenarios e2e).
    prod = yaml.safe_load(DYNAMIC_PROD.read_text(encoding="utf-8"))["http"]["middlewares"]
    stricte = prod["backoffice-login-rate-limit"]["rateLimit"]
    login = prod["auth-signup-rate-limit"]["rateLimit"]
    assert stricte["average"] < login["average"] and stricte["burst"] < login["burst"]
    # En production, le back-office reste eteint tant qu'aucun verificateur reel n'est branche :
    # jamais de faux adaptateur, jamais d'activation par defaut.
    environment = compose["services"]["auth"]["environment"]
    assert "APP_BACKOFFICE_ENABLED" not in environment
    assert "APP_FACE_VERIFIER" not in environment


def test_le_backoffice_n_est_servi_que_sur_l_origine_admin() -> None:
    for chemin in (DYNAMIC_PROD, DYNAMIC_DEV):
        http = yaml.safe_load(chemin.read_text(encoding="utf-8"))["http"]
        routeur = http["routers"]["backoffice"]
        assert routeur["rule"].startswith("HostRegexp("), chemin.name
        assert "!PathPrefix(`/api`)" in routeur["rule"]
        assert routeur["priority"] > http["routers"]["front"]["priority"]
