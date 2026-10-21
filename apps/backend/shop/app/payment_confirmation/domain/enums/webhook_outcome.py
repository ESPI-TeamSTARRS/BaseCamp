from enum import StrEnum


class WebhookOutcome(StrEnum):
    APPLIED = "applied"
    IGNORED = "ignored"
    REPLAYED = "replayed"
