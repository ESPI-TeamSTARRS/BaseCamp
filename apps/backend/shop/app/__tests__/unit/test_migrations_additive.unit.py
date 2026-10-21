"""Une migration ne doit rien casser pour la version precedente du code.

Le retour arriere automatique du deploiement ne restaure pas les bases : l'ancienne image doit
tourner sur le schema migre. Les migrations apres la 0002 ne font donc qu'ajouter (tables,
index, colonnes optionnelles), jamais supprimer ni modifier l'existant.
"""

import ast
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"
ADDITIVE_OPERATIONS = {"create_table", "create_index"}
LAST_BASELINE_REVISION = 2


def _revision(path: Path) -> int:
    match = re.match(r"^(\d+)_", path.name)
    assert match, path.name
    return int(match.group(1))


def _upgrade_operations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrade = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    return [
        node.func.attr
        for node in ast.walk(upgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    ]


def test_migrations_after_the_baseline_only_add() -> None:
    offenders = {
        path.name: sorted(set(_upgrade_operations(path)) - ADDITIVE_OPERATIONS)
        for path in sorted(VERSIONS.glob("*.py"))
        if _revision(path) > LAST_BASELINE_REVISION
    }

    assert {name: ops for name, ops in offenders.items() if ops} == {}


def test_the_orders_migration_exists_and_creates_the_three_tables() -> None:
    (path,) = VERSIONS.glob("0003_*.py")

    assert _upgrade_operations(path).count("create_table") == 3
