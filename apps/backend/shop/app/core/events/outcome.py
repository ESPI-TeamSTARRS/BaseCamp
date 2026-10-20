from enum import StrEnum


class Outcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"
