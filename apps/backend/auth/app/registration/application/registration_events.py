"""Catalogue des evenements metier de la tranche (noms et motifs stables, jamais renommes)."""

ACCOUNT_REGISTERED = "auth.account_registered"
REGISTRATION_REJECTED = "auth.registration_rejected"
EMAIL_VERIFIED = "auth.email_verified"
EMAIL_VERIFICATION_FAILED = "auth.email_verification_failed"
EMAIL_DELIVERY_FAILED = "auth.email_delivery_failed"

REASON_EMAIL_ALREADY_USED = "email_already_used"
REASON_WEAK_PASSWORD = "weak_password"  # noqa: S105
REASON_INVALID_EMAIL = "invalid_email"
REASON_INVALID_TOKEN = "invalid_or_expired_token"  # noqa: S105
REASON_MAIL_DELIVERY_FAILED = "mail_delivery_failed"

RESOURCE_ACCOUNT = "account"
RESOURCE_VERIFICATION = "email_verification"
