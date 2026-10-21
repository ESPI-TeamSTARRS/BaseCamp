from enum import StrEnum


class WeakPasswordReason(StrEnum):
    TOO_SHORT = "password_too_short"
    TOO_LONG = "password_too_long"
    TOO_COMMON = "password_too_common"
