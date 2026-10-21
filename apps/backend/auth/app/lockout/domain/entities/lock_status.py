from dataclasses import dataclass


@dataclass(frozen=True)
class LockStatus:
    """Reponse du verrouillage a l'etape appelante : verrouille ou non, et pour combien de temps."""

    locked: bool
    retry_after_seconds: int = 0
    just_locked: bool = False

    @classmethod
    def free(cls) -> "LockStatus":
        return cls(locked=False)
