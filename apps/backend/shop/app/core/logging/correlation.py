import re
import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-ID"

_VALID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_current: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def is_valid_correlation_id(value: str | None) -> bool:
    return value is not None and _VALID.fullmatch(value) is not None


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> None:
    _current.set(value)


def clear_correlation_id() -> None:
    _current.set(None)


def current_correlation_id() -> str:
    """Identifiant de la requete en cours; hors requete, un identifiant frais est genere."""
    return _current.get() or new_correlation_id()


def outbound_headers() -> dict[str, str]:
    """En-tetes a joindre aux appels vers un autre service pour garder la meme correlation."""
    return {CORRELATION_HEADER: current_correlation_id()}
