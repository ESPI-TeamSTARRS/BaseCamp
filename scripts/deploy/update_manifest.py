#!/usr/bin/env python3
"""Met a jour deploy/manifest.json avec les images publiees par un run de release.

Chaque image publiee est decrite par un petit fichier JSON (`image-<service>.json`) :
    {"service": "shop", "version": "0.1.3", "image": "ghcr.io/o/basecamp-shop@sha256:<64 hex>"}

Utilisation :
    update_manifest.py <manifeste.json> <image-*.json ...>   ecrit le manifeste a jour sur la sortie
    standard et affiche sur la sortie d'erreur le resume des changements (une ligne par composant).

Seuls les composants dont l'image change sont modifies. Le resultat est valide par manifest.py
avant d'etre rendu : un fichier d'image mal forme ne peut pas produire un manifeste invalide.
Code de sortie 0 si au moins un composant change, 10 si rien ne change, 1 en cas d'erreur.

    update_manifest.py describe <ancien.json> <nouveau.json>   resume des differences, une ligne par composant
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
        if service not in result["services"]:
            raise manifest.ManifestError(f"composant inconnu : {service!r}")
        entry = {"version": update.get("version"), "image": update.get("image")}
        if result["services"][service] != entry:
            old = result["services"][service]["version"]
            result["services"][service] = entry
            changes.append(f"{service} {old} -> {entry['version']}")
    manifest.validate(result)
    return result, changes


def describe(old: dict, new: dict) -> list[str]:
    return [
        f"{name} {old['services'][name]['version']} -> {entry['version']}"
        for name, entry in sorted(new["services"].items())
        if old["services"][name] != entry
    ]


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "describe":
        try:
            old = manifest.load(Path(argv[2]).read_text(encoding="utf-8"))
            new = manifest.load(Path(argv[3]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"lecture impossible : {exc}", file=sys.stderr)
            return 1
        print("\n".join(describe(old, new)))
        return 0
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    try:
        current = manifest.load(Path(argv[1]).read_text(encoding="utf-8"))
        updates = [json.loads(Path(p).read_text(encoding="utf-8")) for p in argv[2:]]
        merged, changes = merge(current, updates)
    except (OSError, ValueError) as exc:
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
