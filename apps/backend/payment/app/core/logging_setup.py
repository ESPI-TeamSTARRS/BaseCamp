import logging

from app.core.config import Settings
from app.core.secret_redaction_filter import SecretRedactionFilter

_FRAMEWORK_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access")


def install_log_redaction(settings: Settings) -> None:
    """Masque secrets et numéros de carte dans les journaux techniques (uvicorn, bibliothèques).

    Les événements métier passent par `BusinessEventLogger` (voir docs/development/logging.md);
    ce filtre couvre le reste, par exemple la pile d'une exception inattendue. Idempotent.
    """
    redaction = SecretRedactionFilter([*settings.service_tokens.values(), settings.db_password])
    for name in _FRAMEWORK_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            for old in [f for f in handler.filters if isinstance(f, SecretRedactionFilter)]:
                handler.removeFilter(old)
            handler.addFilter(redaction)
