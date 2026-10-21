"""Catalogue des evenements metier de la tranche (noms et motifs stables, jamais renommes)."""

RESET_REQUESTED = "auth.password_reset_requested"
RESET_COMPLETED = "auth.password_reset_completed"
RESET_REJECTED = "auth.password_reset_rejected"
EMAIL_DELIVERY_FAILED = "auth.email_delivery_failed"

REASON_UNKNOWN_ACCOUNT = "unknown_account"
REASON_INVALID_EMAIL = "invalid_email"
REASON_RATE_LIMITED = "rate_limited"
REASON_WEAK_PASSWORD = "weak_password"  # noqa: S105
REASON_INVALID_TOKEN = "invalid_or_expired_token"  # noqa: S105
REASON_MAIL_DELIVERY_FAILED = "mail_delivery_failed"

RESOURCE_ACCOUNT = "account"
RESOURCE_PASSWORD_RESET = "password_reset"  # noqa: S105

KIND_RESET_LINK = "password_reset"
KIND_PASSWORD_CHANGED = "password_changed"  # noqa: S105
