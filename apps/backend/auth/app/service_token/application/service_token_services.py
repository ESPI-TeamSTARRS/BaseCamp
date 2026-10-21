from dataclasses import dataclass

from app.service_token.application.issue_service_token import IssueServiceTokenUseCase


@dataclass(frozen=True)
class ServiceTokenServices:
    """Cas d'usage de la tranche, cables dans wiring.py et lus par la presentation."""

    issue: IssueServiceTokenUseCase
