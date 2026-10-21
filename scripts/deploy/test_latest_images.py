import importlib.util
from pathlib import Path

HERE = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location("latest_images", HERE / "latest_images.py")
assert _SPEC and _SPEC.loader
latest_images = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(latest_images)

D = "sha256:" + "a" * 64
TAGS = ["shop-v0.9.0", "shop-v0.10.0", "shop-v0.8.0", "auth-v0.9.0", "frontend-v1.0.0", "shop-v0.10.0-rc1"]


def test_versions_triees_en_semver_pas_en_texte() -> None:
    assert latest_images.versions_of("shop", TAGS) == [(0, 10, 0), (0, 9, 0), (0, 8, 0)]


def test_prend_la_derniere_version_dont_l_image_existe() -> None:
    seen: list[str] = []

    def digest_of(ref: str) -> str | None:
        seen.append(ref)
        return D if ref.endswith(":0.9.0") else None

    entry = latest_images.latest("Org", "shop", TAGS, digest_of)
    assert entry == {"service": "shop", "version": "0.9.0", "image": f"ghcr.io/org/basecamp-shop@{D}"}
    assert seen[0].endswith(":0.10.0")  # tag git sans image : ignore


def test_aucun_tag_ou_aucune_image_donne_rien() -> None:
    assert latest_images.latest("o", "payment", TAGS, lambda ref: D) is None
    assert latest_images.latest("o", "shop", TAGS, lambda ref: None) is None


def test_refuse_un_digest_mal_forme() -> None:
    assert latest_images.latest("o", "auth", TAGS, lambda ref: "latest") is None


def test_un_service_ne_prend_pas_les_tags_d_un_autre() -> None:
    assert latest_images.versions_of("auth", ["auth-v0.9.0", "payment-auth-v1.0.0"]) == [(0, 9, 0)]
