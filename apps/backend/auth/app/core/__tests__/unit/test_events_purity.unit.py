"""Le port de journalisation est du Python pur : aucune dependance hors bibliotheque standard."""

import ast
import sys
from pathlib import Path

OWN_PACKAGE = "app.core.events"
EVENTS_ROOT = Path(__file__).resolve().parents[2] / "events"


def test_events_package_imports_only_the_standard_library() -> None:
    offenders: list[str] = []
    for file in EVENTS_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
            offenders += [
                f"{file.name}: {name}"
                for name in names
                if name.split(".")[0] not in sys.stdlib_module_names
                and not name.startswith(OWN_PACKAGE)
            ]
    assert not offenders, "\n".join(offenders)
