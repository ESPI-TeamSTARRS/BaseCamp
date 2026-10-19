from app.health.application.get_health import GetHealthUseCase
from app.health.domain.enums.service_status import ServiceStatus


class TestGetHealthUseCase:
    def test_reports_service_up(self) -> None:
        result = GetHealthUseCase(service_name="payment").execute()
        assert result.service == "payment"
        assert result.status is ServiceStatus.UP
