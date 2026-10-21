from enum import StrEnum


class DiscrepancyKind(StrEnum):
    INTENT_BALANCE = "intent_balance"
    TRANSACTION_UNBALANCED = "transaction_unbalanced"
