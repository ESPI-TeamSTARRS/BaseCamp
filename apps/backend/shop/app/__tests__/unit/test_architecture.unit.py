"""Garde-fou Clean Architecture : verifie la regle de dependance entre couches."""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

# couche -> couches qu'elle n'a PAS le droit d'importer
FORBIDDEN: dict[str, set[str]] = {
    "domain": {"application", "infrastructure", "presentation"},
    "application": {"infrastructure", "presentation"},
    "infrastructure": {"application", "presentation"},
    "presentation": {"domain", "infrastructure"},
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_layers_respect_dependency_rule() -> None:
    violations: list[str] = []
    for file in APP_ROOT.rglob("*.py"):
        if "__tests__" in file.parts:
            continue
        parts = file.relative_to(APP_ROOT).parts
        layer = next((p for p in parts if p in FORBIDDEN), None)
        if layer is None:
            continue
        for module in _imports(file):
            segments = module.split(".")
            hit = FORBIDDEN[layer] & set(segments[1:])
            if segments[0] == "app" and hit:
                violations.append(f"{file.relative_to(APP_ROOT)} ({layer}) importe {module}")
    assert not violations, "\n".join(violations)
