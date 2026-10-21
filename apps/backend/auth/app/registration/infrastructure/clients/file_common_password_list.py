from pathlib import Path

from app.registration.domain.interfaces.common_password_list import CommonPasswordList

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "common_passwords.txt"


class FileCommonPasswordList(CommonPasswordList):
    """Liste embarquee dans le service (donnee statique chargee au demarrage, en minuscules)."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        self._passwords = frozenset(line.strip().lower() for line in lines if line.strip())

    def contains(self, password: str) -> bool:
        return password.lower() in self._passwords
