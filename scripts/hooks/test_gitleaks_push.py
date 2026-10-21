import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "gitleaks_push", Path(__file__).with_name("gitleaks_push.py")
)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)
scan_range = module.scan_range

ZERO = "0" * 40


def test_push_vers_main_utilise_la_plage_du_push() -> None:
    assert scan_range("bbb", "aaa", "refs/heads/main") == "aaa..bbb"


def test_nouvelle_branche_utilise_la_plage_depuis_main() -> None:
    assert scan_range("bbb", ZERO, "refs/heads/feat/x") == "origin/main..bbb"


def test_branche_existante_scanne_comme_une_pr() -> None:
    assert scan_range("bbb", "aaa", "refs/heads/feat/x") == "origin/main..bbb"


def test_premier_push_de_main_retombe_sur_origin_main() -> None:
    assert scan_range("bbb", ZERO, "refs/heads/main") == "origin/main..bbb"
