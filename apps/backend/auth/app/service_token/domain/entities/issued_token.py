from dataclasses import dataclass, field


@dataclass(frozen=True)
class IssuedToken:
    access_token: str = field(repr=False)
    expires_in: int
    scope: str
