import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_commit_msg", Path(__file__).with_name("check_commit_msg.py")
)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def test_accepts_conventional_commit() -> None:
    assert module.is_valid("feat(payment): ajoute le remboursement")


def test_accepts_breaking_change_marker() -> None:
    assert module.is_valid("fix!: corrige le calcul du grand livre")


def test_rejects_free_text() -> None:
    assert not module.is_valid("j ai modifie des trucs")


def test_accepts_merge_commits() -> None:
    assert module.is_valid("Merge branch main")


def test_first_subject_line_skips_comments() -> None:
    assert module.first_subject_line("# commentaire\n\nfeat: ok\n") == "feat: ok"
