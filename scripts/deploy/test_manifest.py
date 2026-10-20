import importlib.util
import io
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("manifest", Path(__file__).with_name("manifest.py"))
assert _SPEC and _SPEC.loader
manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(manifest)

D = "sha256:" + "a" * 64


def sample(**overrides: str) -> dict:
    services = {
        name: {"version": "0.1.0", "image": f"ghcr.io/o/basecamp-{name}@{D}"}
        for name in ("frontend", "shop", "auth", "payment")
    }
    for name, image in overrides.items():
        services[name]["image"] = image
    return {"schema": 1, "services": services}


def test_manifeste_valide() -> None:
    manifest.validate(sample())


def test_refuse_un_tag_a_la_place_du_digest() -> None:
    with pytest.raises(manifest.ManifestError, match="jamais un tag"):
        manifest.validate(sample(shop="ghcr.io/o/basecamp-shop:0.1.0"))


def test_refuse_un_composant_manquant() -> None:
    data = sample()
    del data["services"]["auth"]
    with pytest.raises(manifest.ManifestError, match="services attendus"):
        manifest.validate(data)


def test_refuse_une_version_non_semver() -> None:
    data = sample()
    data["services"]["shop"]["version"] = "latest"
    with pytest.raises(manifest.ManifestError, match="semver"):
        manifest.validate(data)


def test_refuse_un_schema_inconnu() -> None:
    data = sample()
    data["schema"] = 2
    with pytest.raises(manifest.ManifestError, match="schema"):
        manifest.validate(data)


def test_identifiant_ignore_les_versions_et_depend_des_digests() -> None:
    a = sample()
    b = sample()
    b["services"]["shop"]["version"] = "9.9.9"
    c = sample(shop=f"ghcr.io/o/basecamp-shop@sha256:{'b' * 64}")
    assert manifest.release_id(a) == manifest.release_id(b)
    assert manifest.release_id(a) != manifest.release_id(c)


def test_variables_d_environnement() -> None:
    env = manifest.to_env(sample()).splitlines()
    assert f"FRONT_IMAGE=ghcr.io/o/basecamp-frontend@{D}" in env
    assert f"SHOP_IMAGE=ghcr.io/o/basecamp-shop@{D}" in env
    assert len(env) == 4


def test_liste_des_services_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_SERVICES", "shop")
    data = {"schema": 1, "services": {"shop": sample()["services"]["shop"]}}
    manifest.validate(data)
    assert manifest.to_env(data).startswith("SHOP_IMAGE=")


def test_cli_manifeste_illisible(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{pas du json"))
    assert manifest.main(["manifest.py", "validate"]) == 1
    assert "manifeste invalide" in capsys.readouterr().err


def test_cli_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(sample())))
    assert manifest.main(["manifest.py", "env"]) == 0
    assert "SHOP_IMAGE=" in capsys.readouterr().out


def test_cli_refuse_les_arguments_de_chemin() -> None:
    assert manifest.main(["manifest.py", "env", "/etc/passwd"]) == 2


def test_accepte_un_registre_avec_port() -> None:
    manifest.validate(sample(shop=f"localhost:5055/dt@{D}"))
