import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = _load("manifest")
update = _load("update_manifest")

D = "sha256:" + "a" * 64
E = "sha256:" + "b" * 64


def current() -> dict:
    return {
        "schema": 1,
        "services": {
            n: {"version": "0.1.0", "image": f"ghcr.io/o/basecamp-{n}@{D}"}
            for n in ("frontend", "shop", "auth", "payment")
        },
    }


def test_met_a_jour_seulement_le_composant_publie() -> None:
    new = {"service": "shop", "version": "0.1.1", "image": f"ghcr.io/o/basecamp-shop@{E}"}
    merged, changes = update.merge(current(), [new])
    assert merged["services"]["shop"]["version"] == "0.1.1"
    assert merged["services"]["auth"] == current()["services"]["auth"]
    assert changes == ["shop 0.1.0 -> 0.1.1"]


def test_rien_a_changer_si_meme_image() -> None:
    same = {"service": "shop", **current()["services"]["shop"]}
    _, changes = update.merge(current(), [same])
    assert changes == []


def test_refuse_un_composant_inconnu() -> None:
    with pytest.raises(update.manifest.ManifestError, match="inconnu"):
        update.merge(current(), [{"service": "mail", "version": "1.0.0", "image": f"x/y@{D}"}])


def test_refuse_une_image_par_tag() -> None:
    bad = {"service": "shop", "version": "0.1.1", "image": "ghcr.io/o/basecamp-shop:0.1.1"}
    with pytest.raises(update.manifest.ManifestError, match="jamais un tag"):
        update.merge(current(), [bad])


def test_cli_code_10_sans_changement(tmp_path: Path) -> None:
    base = tmp_path / "m.json"
    base.write_text(json.dumps(current()), encoding="utf-8")
    img = tmp_path / "image-shop.json"
    img.write_text(json.dumps({"service": "shop", **current()["services"]["shop"]}), encoding="utf-8")
    assert update.main(["u", str(base), str(img)]) == update.NO_CHANGE


def test_cli_ecrit_le_manifeste(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = tmp_path / "m.json"
    base.write_text(json.dumps(current()), encoding="utf-8")
    img = tmp_path / "image-shop.json"
    img.write_text(
        json.dumps({"service": "shop", "version": "0.2.0", "image": f"ghcr.io/o/basecamp-shop@{E}"}),
        encoding="utf-8",
    )
    assert update.main(["u", str(base), str(img)]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["services"]["shop"]["version"] == "0.2.0"
    assert "shop 0.1.0 -> 0.2.0" in out.err


def test_le_manifeste_versionne_est_valide() -> None:
    path = HERE.parent.parent / "deploy" / "manifest.json"
    manifest.validate(manifest.load(path.read_text(encoding="utf-8")))


def test_resume_des_differences() -> None:
    new = json.loads(json.dumps(current()))
    new["services"]["auth"] = {"version": "0.3.0", "image": f"ghcr.io/o/basecamp-auth@{E}"}
    assert update.describe(current(), new) == ["auth 0.1.0 -> 0.3.0"]
