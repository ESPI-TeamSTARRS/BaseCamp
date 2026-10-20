import pytest

from app.health.domain.entities.health_status import HealthStatus
from app.health.domain.enums.service_status import ServiceStatus


class TestHealthStatus:
    def test_rejects_blank_service_name(self) -> None:
        """Etant donne un nom vide, quand on cree l'etat, alors une erreur est levee."""
        with pytest.raises(ValueError):
            HealthStatus(service="  ", status=ServiceStatus.UP)

    def test_keeps_service_and_status(self) -> None:
        status = HealthStatus(service="payment", status=ServiceStatus.UP)
        assert status.service == "payment"
        assert status.status is ServiceStatus.UP

    def test_is_up_only_when_status_is_up(self) -> None:
        assert HealthStatus(service="shop", status=ServiceStatus.UP).is_up is True
        assert HealthStatus(service="shop", status=ServiceStatus.DOWN).is_up is False
