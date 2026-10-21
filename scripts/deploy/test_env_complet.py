"""Chaque variable obligatoire de la pile de production doit etre produite par l'installation."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
EXAMPLE = ROOT / "deploy" / "prod.env.example"
SCRIPT = ROOT / "infra" / "complete-env.sh"

# Fournies par le manifeste de release (scripts/deploy/manifest.py), pas par le .env.
FROM_MANIFEST = {"FRONT_IMAGE", "SHOP_IMAGE", "PAYMENT_IMAGE", "AUTH_IMAGE"}
# Variables obligatoires dont la valeur est choisie par l'operateur et non generee.
OPERATOR_CHOSEN = {"BASECAMP_DOMAIN"}


def required_variables() -> set[str]:
    return set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", COMPOSE.read_text(encoding="utf-8")))


def generated_variables() -> set[str]:
    text = EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=change-me$", text, flags=re.MULTILINE))


def test_chaque_variable_obligatoire_est_produite_par_l_installation() -> None:
    missing = required_variables() - FROM_MANIFEST - OPERATOR_CHOSEN - generated_variables()
    assert not missing, f"variables obligatoires non generees par l'installation : {sorted(missing)}"


def test_le_domaine_est_dans_le_modele() -> None:
    assert re.search(r"^BASECAMP_DOMAIN=", EXAMPLE.read_text(encoding="utf-8"), flags=re.MULTILINE)


skip_bash = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("openssl") is None or (sys.platform == "win32" and "TEST_BASH" not in os.environ),
    reason="bash/openssl absents, ou Windows sans TEST_BASH",
)


def run(env_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [os.environ.get("TEST_BASH", "bash"), SCRIPT.as_posix(), EXAMPLE.as_posix(), env_file.as_posix()],
        capture_output=True,
        text=True,
        check=False,
    )


def values(env_file: Path) -> dict[str, str]:
    out = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, _, value = line.partition("=")
            out[key] = value
    return out


@skip_bash
def test_complete_un_fichier_absent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    assert run(env_file).returncode == 0
    result = values(env_file)
    assert generated_variables() <= {k for k, v in result.items() if len(v) >= 32}


@skip_bash
def test_ne_modifie_pas_les_valeurs_renseignees_et_ne_les_affiche_pas(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SHOP_DB_PASSWORD=ma-valeur-secrete\nBASECAMP_DOMAIN=exemple.test", encoding="utf-8")
    result = run(env_file)
    assert result.returncode == 0
    assert "ma-valeur-secrete" not in result.stdout + result.stderr
    final = values(env_file)
    assert final["SHOP_DB_PASSWORD"] == "ma-valeur-secrete"
    assert final["BASECAMP_DOMAIN"] == "exemple.test"  # derniere ligne sans retour a la ligne : non fusionnee
    assert len(final["AUTH_DB_PASSWORD"]) >= 32


@skip_bash
def test_remplit_une_valeur_vide_et_est_idempotent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_DB_PASSWORD=\n", encoding="utf-8")
    assert run(env_file).returncode == 0
    first = values(env_file)
    assert len(first["AUTH_DB_PASSWORD"]) >= 32
    assert run(env_file).returncode == 0
    assert values(env_file) == first


def test_l_installation_ne_conseille_jamais_de_supprimer_l_ancienne_pile() -> None:
    script = (ROOT / "infra" / "install-vm.sh").read_text(encoding="utf-8")
    assert "docker compose down" not in script
    assert "stop, jamais down" in script


def test_l_installation_conserve_l_etat_du_minuteur() -> None:
    script = (ROOT / "infra" / "install-vm.sh").read_text(encoding="utf-8")
    # Rechargement des unites sans restart/disable : l'etat actif/active d'un minuteur existant est conserve.
    assert "daemon-reload" in script
    assert "systemctl restart basecamp-deploy" not in script
    assert "systemctl disable" not in script
