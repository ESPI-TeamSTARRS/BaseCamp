from enum import StrEnum


class PaymentMethod(StrEnum):
    """Seules méthodes acceptées : aucune donnée bancaire (ni numéro de carte) n'entre dans payment."""

    SUCCESS = "pm_test_success"
    DECLINED = "pm_test_declined"
    TIMEOUT = "pm_test_timeout"
