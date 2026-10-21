from enum import StrEnum


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD = "dead"
