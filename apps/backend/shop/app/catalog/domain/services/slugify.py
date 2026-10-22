import re
import unicodedata

_MAX_LENGTH = 128
_SEPARATORS = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """`Tente Tunnel 4 Saisons` -> `tente-tunnel-4-saisons` (accents retirés, 128 caractères au plus)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _SEPARATORS.sub("-", ascii_name.lower()).strip("-")[:_MAX_LENGTH].strip("-")
