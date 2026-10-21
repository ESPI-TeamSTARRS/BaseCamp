"""Noms des evenements de garde-fou du service (catalogue : docs/services/payment.md).

Centralises ici pour rester faciles a renommer : un nom publie ne change plus ensuite.
"""

PAYLOAD_TOO_LARGE = "service.payload_too_large"  # 413
REQUEST_TIMEOUT = "service.request_timeout"  # 408 / 504
OVERLOADED = "service.overloaded"  # 503, plafond de requetes simultanees
RATE_LIMITED = "service.rate_limited"  # 429
DATABASE_UNAVAILABLE = "service.database_unavailable"  # 503
