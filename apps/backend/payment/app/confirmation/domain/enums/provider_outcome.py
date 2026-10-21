from enum import StrEnum


class ProviderOutcome(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"
