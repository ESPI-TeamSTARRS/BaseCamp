"""Applique automatiquement le marker pytest selon le suffixe du fichier de test."""

import os

import pytest

_LEVEL_BY_SUFFIX = {".unit.py": "unit", ".integ.py": "integ", ".e2e.py": "e2e"}
_E2E_URL_VARIABLE = "E2E_BASE_URL"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    stack_available = bool(os.environ.get(_E2E_URL_VARIABLE))
    skip_e2e = pytest.mark.skip(reason=f"pile non lancee : definir {_E2E_URL_VARIABLE}")
    for item in items:
        for suffix, marker in _LEVEL_BY_SUFFIX.items():
            if item.path.name.endswith(suffix):
                item.add_marker(marker)
                if marker == "e2e" and not stack_available:
                    item.add_marker(skip_e2e)
                break


@pytest.fixture(autouse=True)
def _static_jwks(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Tests unitaires et d'integration : les cles d'`auth` sont celles de la cle de test, sans reseau.

    Un test qui veut sa propre source la passe a `create_app(..., jwks_source=...)`.
    """
    if request.node.get_closest_marker("e2e"):
        return
    from app.caller_identity.__tests__.tokens import JWKS

    monkeypatch.setattr("app.caller_identity.wiring.HttpJwksSource", lambda client, url: JWKS)
