"""Une migration ne doit rien casser pour la version precedente du code.

Le retour arriere automatique du deploiement ne restaure pas les bases : l'ancienne image doit
tourner sur le schema migre. Les migrations apres la 0002 ne font donc qu'ajouter (tables,
index, colonnes NULLABLES), jamais supprimer ni modifier l'existant.
"""

import ast
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"
ADDITIVE_OPERATIONS = {"create_table", "create_index", "add_column"}
# Elargir une contrainte CHECK de statut (ajout d'une valeur) reste compatible : l'ancien code
# n'ecrit que les anciennes valeurs. Seules les contraintes listees ici peuvent etre remplacees.
WIDENABLE_CONSTRAINTS = {"ck_orders_status", "ck_stock_reservations_status"}
CONSTRAINT_OPERATIONS = {"drop_constraint", "create_check_constraint"}
LAST_BASELINE_REVISION = 2
NL = chr(10)


def _revision(path: Path) -> int:
    match = re.match(r"^(\d+)_", path.name)
    assert match, path.name
    return int(match.group(1))


def _upgrade_operations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrade = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    operations: list[str] = []
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            continue
        name = node.func.attr
        if name in CONSTRAINT_OPERATIONS and _first_string(node) in WIDENABLE_CONSTRAINTS:
            continue
        if name == "add_column" and not _is_nullable_column(node):
            operations.append("add_column_not_nullable")
            continue
        operations.append(name)
    return operations


def _is_nullable_column(call: ast.Call) -> bool:
    """Une colonne ajoutee doit etre nullable : l'ancien code ne la renseigne pas."""
    for argument in call.args:
        if isinstance(argument, ast.Call):
            return any(
                keyword.arg == "nullable"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in argument.keywords
            )
    return False


def _first_string(call: ast.Call) -> str | None:
    return next(
        (a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)),
        None,
    )


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


def test_only_the_listed_status_constraints_may_be_replaced(tmp_path: Path) -> None:
    migration = tmp_path / "0099_x.py"
    migration.write_text(
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.drop_constraint('ck_products_stock_non_negative', 'products', type_='check')\n"
        "    op.drop_constraint('ck_orders_status', 'orders', type_='check')\n",
        encoding="utf-8",
    )

    assert _upgrade_operations(migration) == ["drop_constraint"]


def test_the_webhook_migration_adds_its_table_and_only_widens_the_reservation_status() -> None:
    (path,) = VERSIONS.glob("0006_*.py")
    source = path.read_text(encoding="utf-8")

    assert _upgrade_operations(path) == ["create_table"]
    assert "payment_webhook_events" in source
    assert "uq_payment_webhook_events_paid_order_id" in source
    assert "'reserved', 'released', 'committed'" in source


def _migration(tmp_path: Path, name: str, nullable: bool) -> Path:
    path = tmp_path / name
    path.write_text(
        "import sqlalchemy as sa"
        + NL
        + "from alembic import op"
        + NL
        + "def upgrade():"
        + NL
        + f"    op.add_column('t', sa.Column('c', sa.String(3), nullable={nullable}))"
        + NL,
        encoding="utf-8",
    )
    return path


def test_an_added_column_must_be_nullable(tmp_path: Path) -> None:
    good = _migration(tmp_path, "0098_good.py", nullable=True)
    bad = _migration(tmp_path, "0099_bad.py", nullable=False)

    assert _upgrade_operations(good) == ["add_column"]
    assert _upgrade_operations(bad) == ["add_column_not_nullable"]
