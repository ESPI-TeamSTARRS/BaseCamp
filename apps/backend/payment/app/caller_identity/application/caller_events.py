"""Evenements d'identification des appelants (noms et motifs stables)."""

AUTHENTICATED = "payment.service_authenticated"  # nom publie depuis WORK-21, conserve
FORBIDDEN = "payment.caller_forbidden"
KEYS_UNAVAILABLE = "payment.keys_unavailable"

REASON_INVALID_TOKEN = "invalid_token"  # noqa: S105
REASON_MISSING_SCOPE = "missing_scope"
REASON_ROLE_REQUIRED = "operator_role_required"
REASON_CLIENT_TOKEN_REFUSED = "client_token_refused"  # noqa: S105
REASON_KEYS_UNAVAILABLE = "keys_unavailable"

ACTOR_SERVICE = "service"
