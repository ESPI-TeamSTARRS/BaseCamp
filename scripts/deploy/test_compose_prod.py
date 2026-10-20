"""Garde-fous de la pile de production (deploy/docker-compose.prod.yml).

Ces tests ne lancent aucun conteneur : ils verifient les invariants du fichier, pour qu'une
modification ne puisse pas rouvrir un port, reintroduire un build ou une image par tag flottant.
"""

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

SAMPLE_ENV = {
    "FRONT_IMAGE": "ghcr.io/o/basecamp-frontend@sha256:" + "a" * 64,
    "SHOP_IMAGE": "ghcr.io/o/basecamp-shop@sha256:" + "b" * 64,
    "PAYMENT_IMAGE": "ghcr.io/o/basecamp-payment@sha256:" + "c" * 64,
    "AUTH_IMAGE": "ghcr.io/o/basecamp-auth@sha256:" + "d" * 64,
    "BASECAMP_DOMAIN": "basecamp.example.test",
    "POSTGRES_ADMIN_PASSWORD": "x",
    "SHOP_DB_PASSWORD": "x",
    "PAYMENT_DB_PASSWORD": "x",
    "PAYMENT_SERVICE_TOKEN_SHOP": "x",
    "AUTH_DB_PASSWORD": "x",
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
    prod_middlewares = {k: v for k, v in prod["middlewares"].items() if k != "orders-rate-limit"}
    dev_middlewares = {k: v for k, v in dev["middlewares"].items() if k != "orders-rate-limit"}
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
