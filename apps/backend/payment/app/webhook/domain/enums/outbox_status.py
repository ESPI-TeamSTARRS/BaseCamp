from enum import StrEnum


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD = "dead"
    REJECTED_BY_RECEIVER = "rejected_by_receiver"  # refusé par la boutique : remboursé
