from enum import StrEnum


class PaymentMethod(StrEnum):
    """Méthodes de test acceptées : aucune donnée bancaire n'est jamais saisie ni transmise."""

    SUCCESS = "pm_test_success"
    DECLINED = "pm_test_declined"
