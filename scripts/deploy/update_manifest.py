#!/usr/bin/env python3
"""Met a jour deploy/manifest.json avec les images publiees par un run de release.

Chaque image publiee est decrite par un petit fichier JSON (`image-<service>.json`) :
    {"service": "shop", "version": "0.1.3", "image": "ghcr.io/o/basecamp-shop@sha256:<64 hex>"}

Utilisation (aucun chemin en argument : tout arrive sur l'entree standard, un document JSON par
ligne, d'abord le manifeste de base puis les images) :
    jq -c . base.json image-*.json | update_manifest.py
ecrit le manifeste a jour sur la sortie standard et affiche sur la sortie d'erreur le resume des
changements (une ligne par composant).

Seuls les composants dont l'image change sont modifies. Le resultat est valide par manifest.py
avant d'etre rendu : un fichier d'image mal forme ne peut pas produire un manifeste invalide.
Code de sortie 0 si au moins un composant change, 10 si rien ne change, 1 en cas d'erreur.

    jq -c . ancien.json nouveau.json | update_manifest.py describe   resume des differences
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest  # noqa: E402

NO_CHANGE = 10


def merge(current: dict, updates: list[dict]) -> tuple[dict, list[str]]:
    """Retourne (nouveau manifeste, lignes de resume)."""
    result = json.loads(json.dumps(current))
    changes: list[str] = []
    for update in updates:
        service = update.get("service")
        if service not in result["services"] and service not in manifest.OPTIONAL_SERVICES:
            raise manifest.ManifestError(f"composant inconnu : {service!r}")
        entry = {"version": update.get("version"), "image": update.get("image")}
        if result["services"].get(service) != entry:
            old = result["services"].get(service, {}).get("version", "absent")
            result["services"][service] = entry
            changes.append(f"{service} {old} -> {entry['version']}")
    manifest.validate(result)
    return result, changes


def describe(old: dict, new: dict) -> list[str]:
    return [
        f"{name} {old['services'].get(name, {}).get('version', 'absent')} -> {entry['version']}"
        for name, entry in sorted(new["services"].items())
        if old["services"].get(name) != entry
    ]


def read_documents() -> list[dict]:
    """Documents JSON de l'entree standard, un par ligne (JSON Lines)."""
    return [json.loads(line) for line in sys.stdin.read().splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    describing = len(argv) == 2 and argv[1] == "describe"
    if len(argv) != 1 and not describing:
        print(__doc__, file=sys.stderr)
        return 1
    try:
        documents = read_documents()
        if describing:
            if len(documents) != 2:
                raise manifest.ManifestError("deux manifestes attendus (ancien puis nouveau)")
            for document in documents:
                manifest.validate(document)
            print("\n".join(describe(documents[0], documents[1])))
            return 0
        if len(documents) < 2:
            raise manifest.ManifestError("un manifeste puis au moins une image attendus")
        manifest.validate(documents[0])
        merged, changes = merge(documents[0], documents[1:])
    except ValueError as exc:
        print(f"mise a jour impossible : {exc}", file=sys.stderr)
        return 1
    if not changes:
        return NO_CHANGE
    for line in changes:
        print(line, file=sys.stderr)
    print(json.dumps(merged, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
