#!/usr/bin/env python3
"""Liste, pour chaque composant, la derniere version publiee (tag git + image GHCR existante).

Utilisation : latest_images.py <proprietaire> <composant>...
Ecrit sur la sortie standard un document JSON par ligne, au format attendu par update_manifest.py :
    {"service": "shop", "version": "0.8.0", "image": "ghcr.io/o/basecamp-shop@sha256:<64 hex>"}

Une version est retenue si son tag git `<composant>-vX.Y.Z` existe ET si l'image `:X.Y.Z` est dans
GHCR (le tag de version n'est pose sur l'image qu'apres les tests et le scan : un tag git sans image
est ignore). Un composant sans aucune image publiee est omis, son entree du manifeste ne change pas.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable

TAG_RE = r"^{service}-v(\d+)\.(\d+)\.(\d+)$"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def versions_of(service: str, tags: list[str]) -> list[tuple[int, int, int]]:
    pattern = re.compile(TAG_RE.format(service=re.escape(service)))
    found = [tuple(int(n) for n in m.groups()) for t in tags if (m := pattern.match(t))]
    return sorted(found, reverse=True)  # type: ignore[arg-type]


def latest(
    owner: str,
    service: str,
    tags: list[str],
    digest_of: Callable[[str], str | None],
) -> dict | None:
    image = f"ghcr.io/{owner.lower()}/basecamp-{service}"
    for version in versions_of(service, tags):
        text = ".".join(str(n) for n in version)
        digest = digest_of(f"{image}:{text}")
        if digest and DIGEST_RE.match(digest):
            return {"service": service, "version": text, "image": f"{image}@{digest}"}
    return None


def git_tags() -> list[str]:
    out = subprocess.run(["git", "tag", "--list"], check=True, capture_output=True, text=True)
    return out.stdout.split()


def registry_digest(ref: str) -> str | None:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{.Manifest.Digest}}"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    owner, services = argv[1], argv[2:]
    tags = git_tags()
    for service in services:
        entry = latest(owner, service, tags, registry_digest)
        if entry is None:
            print(f"{service} : aucune image publiee, entree inchangee.", file=sys.stderr)
            continue
        print(json.dumps(entry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
