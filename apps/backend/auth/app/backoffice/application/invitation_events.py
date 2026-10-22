"""Evenements metier des invitations d'operateur (noms et motifs stables).

Jamais de jeton, d'image, de gabarit, de mot de passe ni d'email en clair : seulement l'empreinte de
l'email (`email_hash`) et, sur les refus de la route publique, l'adresse du client.
"""

OPERATOR_INVITE_CREATED = "auth.operator_invite_created"
OPERATOR_INVITE_CONSUMED = "auth.operator_invite_consumed"
OPERATOR_INVITE_REVOKED = "auth.operator_invite_revoked"
OPERATOR_INVITE_REFUSED = "auth.operator_invite_refused"

REASON_INVALID_TOKEN = "invalid_token"  # noqa: S105
REASON_STEP_LOCKED = "step_locked"
REASON_WEAK_PASSWORD = "weak_password"  # noqa: S105
REASON_PHOTO_COUNT = "photo_count"
REASON_INVALID_PHOTO = "invalid_photo"
REASON_NO_FACE = "no_face"
REASON_ACCOUNT_EXISTS = "account_exists"
REASON_INVALID_EMAIL = "invalid_email"

RESOURCE_INVITATION = "operator_invitation"
RESOURCE_ACCOUNT = "account"
ACTOR_CLI = "cli"
