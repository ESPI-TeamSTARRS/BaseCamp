"""Applique automatiquement le marker pytest selon le suffixe du fichier de test."""

import pytest

_LEVEL_BY_SUFFIX = {".unit.py": "unit", ".integ.py": "integ", ".e2e.py": "e2e"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for suffix, marker in _LEVEL_BY_SUFFIX.items():
            if item.path.name.endswith(suffix):
                item.add_marker(marker)
                break
