"""Tests de scripts/pull-deploy.sh avec un depot 'origin' local et un deploy.sh factice."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pull-deploy.sh"

# Sous Windows, `bash` est souvent le lanceur WSL : on ne joue ces tests que si TEST_BASH (Git Bash) est fourni.
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("git") is None
    or (sys.platform == "win32" and "TEST_BASH" not in os.environ),
    reason="bash/git absents, ou Windows sans TEST_BASH",
)


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def env(tmp_path: Path) -> dict:
    origin = tmp_path / "origin"
    (origin / "scripts").mkdir(parents=True)
    (origin / "deploy").mkdir()
    # deploy.sh factice : consigne l'appel et le manifeste recu.
    (origin / "scripts" / "deploy.sh").write_text(
        '#!/usr/bin/env bash\necho "appel:$1" > "$BASECAMP_STATE_DIR/appel.txt"\ncat "$1" >> "$BASECAMP_STATE_DIR/appel.txt"\n',
        encoding="utf-8",
    )
    (origin / "deploy" / "manifest.json").write_text('{"v": 1}\n', encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main", str(origin))
    git(origin, "add", "-A")
    git(origin, "update-index", "--chmod=+x", "scripts/deploy.sh")
    git(origin, "commit", "-q", "-m", "init")
    repo = tmp_path / "repo"
    git(tmp_path, "clone", "-q", origin.as_posix(), repo.as_posix())
    state = tmp_path / "state"
    state.mkdir()
    env_file = tmp_path / "env"
    env_file.write_text("A=1\n", encoding="utf-8")
    return {
        **os.environ,
        "BASECAMP_REPO_DIR": repo.as_posix(),
        "BASECAMP_STATE_DIR": state.as_posix(),
        "BASECAMP_ENV_FILE": env_file.as_posix(),
        "BASECAMP_BLOCK_IF_RUNNING": "",
        "_ORIGIN": origin.as_posix(),
    }


def run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([os.environ.get("TEST_BASH", "bash"), SCRIPT.as_posix()], env=env, capture_output=True, text=True, check=False)


def test_deploie_le_manifeste_de_main(env: dict) -> None:
    result = run(env)
    assert result.returncode == 0, result.stderr
    recorded = (Path(env["BASECAMP_STATE_DIR"]) / "appel.txt").read_text(encoding="utf-8")
    assert recorded.startswith("appel:") and recorded.rstrip().endswith('{"v": 1}')


def test_recupere_la_derniere_version_de_main(env: dict) -> None:
    origin = Path(env["_ORIGIN"])
    (origin / "deploy" / "manifest.json").write_text('{"v": 2}\n', encoding="utf-8")
    git(origin, "commit", "-q", "-am", "maj")
    assert run(env).returncode == 0
    assert (Path(env["BASECAMP_STATE_DIR"]) / "appel.txt").read_text(encoding="utf-8").rstrip().endswith('{"v": 2}')


def test_pause_suspend_le_deploiement(env: dict) -> None:
    (Path(env["BASECAMP_STATE_DIR"]) / "PAUSE").write_text("", encoding="utf-8")
    result = run(env)
    assert result.returncode == 0
    assert "pause" in result.stdout
    assert not (Path(env["BASECAMP_STATE_DIR"]) / "appel.txt").exists()


def test_refuse_sans_fichier_d_environnement(env: dict) -> None:
    Path(env["BASECAMP_ENV_FILE"]).write_text("", encoding="utf-8")
    result = run(env)
    assert result.returncode == 1
    assert "absent ou vide" in result.stdout
