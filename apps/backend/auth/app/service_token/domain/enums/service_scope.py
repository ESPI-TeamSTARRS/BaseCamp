from enum import StrEnum

from app.service_token.domain.enums.service_audience import ServiceAudience


class ServiceScope(StrEnum):
    """Permissions accordables à un client de service (liste fermée)."""

    PAYMENTS_WRITE = "payments:write"  # creer, lire, confirmer, annuler un paiement
    REFUNDS_WRITE = "refunds:write"  # rembourser un paiement (jamais accorde a `shop` par defaut)

    @property
    def audience(self) -> ServiceAudience:
        """Le service destinataire auquel ce scope s'applique."""
        return _AUDIENCE_BY_SCOPE[self]


_AUDIENCE_BY_SCOPE: dict[ServiceScope, ServiceAudience] = {
    ServiceScope.PAYMENTS_WRITE: ServiceAudience.PAYMENT,
    ServiceScope.REFUNDS_WRITE: ServiceAudience.PAYMENT,
}
