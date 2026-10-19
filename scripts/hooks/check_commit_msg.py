#!/usr/bin/env python
"""Valide le message de commit : Conventional Commit (description en francais).

Appele par le hook git `commit-msg`. Recoit le chemin du fichier de message.
Format : <type>(<scope>)?!?: <description>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = "feat|fix|docs|chore|refactor|test|ci|build|perf|style|revert"
SUBJECT_RE = re.compile(rf"^(?:{TYPES})(?:\([^)]+\))?!?: .+")
EXEMPT_PREFIXES = ("Merge ", "Revert ", "fixup!", "squash!")


def first_subject_line(raw: str) -> str:
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def is_valid(subject: str) -> bool:
    return subject.startswith(EXEMPT_PREFIXES) or bool(SUBJECT_RE.match(subject))


def main() -> int:
    if len(sys.argv) < 2:
        print("check_commit_msg: chemin du message manquant.", file=sys.stderr)
        return 1
    subject = first_subject_line(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if is_valid(subject):
        return 0
    print(
        "\nMessage de commit non conforme (Conventional Commit).\n"
        f"   Recu : {subject!r}\n"
        "   Attendu : <type>(<scope>)?: <description>\n"
        f"   Types : {TYPES.replace('|', ', ')}\n"
        "   Exemple : feat(payment): ajoute le remboursement partiel\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
