#!/usr/bin/env python3
"""Manifeste de release : validation, identite et conversion en variables d'environnement.

Format (deploy/manifest.json) :

    {"schema": 1,
     "services": {"shop": {"version": "0.1.2", "image": "ghcr.io/o/basecamp-shop@sha256:<64 hex>"}, ...}}

Le manifeste est l'unite de deploiement et de retour arriere : une version de chaque composant, par
digest. Utilisation (appele par scripts/deploy.sh) :

    manifest.py validate < manifeste.json   verifie le format, code 0 si valide
    manifest.py id < manifeste.json         identifiant stable (empreinte des seules images)
    manifest.py env < manifeste.json        lignes VARIABLE=valeur pour docker compose

Le manifeste est lu sur l'entree standard : le script n'ouvre aucun chemin recu en argument.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

DEFAULT_SERVICES = ("frontend", "shop", "auth", "payment")
# Composants facultatifs : acceptes absents (anciens manifestes, retour arriere) ou presents.
# Present, le composant est valide comme les autres et son profil compose est active (COMPOSE_PROFILES).
OPTIONAL_SERVICES = ("backoffice",)
# Variable de compose de chaque composant (le front garde l'historique FRONT_IMAGE).
ENV_NAMES = {"frontend": "FRONT_IMAGE"}
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ManifestError(ValueError):
    """Manifeste invalide."""


def required_services() -> tuple[str, ...]:
    raw = os.environ.get("DEPLOY_SERVICES")
    return tuple(raw.split()) if raw else DEFAULT_SERVICES


def env_name(service: str) -> str:
    return ENV_NAMES.get(service, f"{service.upper()}_IMAGE")


def load(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifeste illisible : {exc}") from exc
    validate(data)
    return data


def validate(data: object) -> None:
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ManifestError("schema 1 attendu")
    services = data.get("services")
    if not isinstance(services, dict):
        raise ManifestError("champ services manquant")
    expected = set(required_services())
    if not expected <= set(services) <= expected | set(OPTIONAL_SERVICES):
        raise ManifestError(
            f"services attendus {sorted(expected)} (facultatifs : {sorted(OPTIONAL_SERVICES)}), "
            f"recus {sorted(services)}"
        )
    for name, entry in services.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"{name} : objet attendu")
        if not VERSION_RE.match(str(entry.get("version", ""))):
            raise ManifestError(f"{name} : version semver attendue")
        if not IMAGE_RE.match(str(entry.get("image", ""))):
            raise ManifestError(f"{name} : image attendue sous la forme depot@sha256:<64 hex> (jamais un tag)")


def release_id(data: dict) -> str:
    """Empreinte des seules images : deux manifestes qui deploient les memes digests sont identiques."""
    images = {name: entry["image"] for name, entry in sorted(data["services"].items())}
    return hashlib.sha256(json.dumps(images, sort_keys=True).encode()).hexdigest()


def to_env(data: dict) -> str:
    lines = [f"{env_name(name)}={entry['image']}" for name, entry in sorted(data["services"].items())]
    profiles = [name for name in OPTIONAL_SERVICES if name in data["services"]]
    if profiles:
        lines.append(f"COMPOSE_PROFILES={','.join(profiles)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"validate", "id", "env"}:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        data = load(sys.stdin.read())
    except ManifestError as exc:
        print(f"manifeste invalide : {exc}", file=sys.stderr)
        return 1
    if argv[1] == "id":
        print(release_id(data))
    elif argv[1] == "env":
        print(to_env(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
