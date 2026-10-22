"""Catalogue des evenements metier de la connexion du back-office (noms et motifs stables).

Aucun evenement ne porte d'image, de score, d'email en clair ni de mot de passe : seulement des
empreintes (`email_hash`) et, sur les refus, l'adresse du client (contrat de logs d'auth).
"""

BACKOFFICE_IDENTIFY = "auth.backoffice_identify"
BACKOFFICE_FACE_RESULT = "auth.backoffice_face_result"
BACKOFFICE_PASSWORD_RESULT = "auth.backoffice_password_result"  # noqa: S105
BACKOFFICE_LOCKOUT = "auth.backoffice_lockout"
BACKOFFICE_FACE_ENROLLED = "auth.backoffice_face_enrolled"
BACKOFFICE_FACE_ENROLLMENT_REFUSED = "auth.backoffice_face_enrollment_refused"

REASON_INVALID_CHALLENGE = "invalid_challenge"
REASON_FACE_REFUSED = "face_refused"
REASON_FACE_REQUIRED = "face_required"
REASON_WRONG_PASSWORD = "wrong_password"  # noqa: S105
REASON_STEP_LOCKED = "step_locked"
REASON_INVALID_TEMPLATE = "invalid_template"
REASON_UNKNOWN_OPERATOR = "unknown_operator"
REASON_PHOTO_COUNT = "photo_count"
REASON_INVALID_PHOTO = "invalid_photo"
REASON_NO_FACE = "no_face"

CAUSE_UNKNOWN_ACCOUNT = "unknown_account"
CAUSE_NO_TEMPLATE = "no_template"
CAUSE_NO_MATCH = "no_match"
CAUSE_ACCOUNT_LOCKED = "account_locked"
CAUSE_ADDRESS_LOCKED = "address_locked"
CAUSE_ACCOUNT_DISABLED = "account_disabled"

RESOURCE_ACCOUNT = "account"
RESOURCE_CHALLENGE = "login_challenge"
ACTOR_USER = "user"
