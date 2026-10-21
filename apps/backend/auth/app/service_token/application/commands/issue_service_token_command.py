from dataclasses import dataclass, field


@dataclass(frozen=True)
class IssueServiceTokenCommand:
    client_id: str
    client_secret: str = field(repr=False)
    audience: str
    scope: str
