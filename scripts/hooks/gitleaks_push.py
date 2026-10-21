#!/usr/bin/env python
"""Scanne avec gitleaks les commits qu'un push apporte, comme le job `secrets-scan` de la CI.

Appele par le hook git `pre-push` (via pre-commit, qui fournit PRE_COMMIT_TO_REF et
PRE_COMMIT_REMOTE_BRANCH). Meme config (`.gitleaks.toml`, `.gitleaksignore`) que la CI :
- push vers main : plage FROM..TO du push ;
- autre branche : tout ce que TO ajoute a origin/main (plage d'une PR).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ZEROS = "0" * 7


def scan_range(to_ref: str, from_ref: str, remote_branch: str) -> str:
    if remote_branch == "refs/heads/main" and from_ref and not from_ref.startswith(ZEROS):
        return f"{from_ref}..{to_ref}"
    return f"origin/main..{to_ref}"


def main() -> int:
    to_ref = os.environ.get("PRE_COMMIT_TO_REF", "")
    if not to_ref or to_ref.startswith(ZEROS):
        return 0  # suppression de branche : rien a scanner
    binary = shutil.which("gitleaks")
    if binary is None:
        print(
            "gitleaks_push: binaire `gitleaks` introuvable. Installez-le (v8.30.1) : "
            "https://github.com/gitleaks/gitleaks#installing",
            file=sys.stderr,
        )
        return 1
    rng = scan_range(
        to_ref,
        os.environ.get("PRE_COMMIT_FROM_REF", ""),
        os.environ.get("PRE_COMMIT_REMOTE_BRANCH", ""),
    )
    print(f"gitleaks sur {rng}")
    return subprocess.run([binary, "git", "--redact", "-v", f"--log-opts={rng}", "."]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
