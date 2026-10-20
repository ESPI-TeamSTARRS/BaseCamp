from app.health.application.get_readiness import GetReadinessUseCase
from app.health.domain.enums.service_status import ServiceStatus
from app.health.domain.interfaces.database_probe import DatabaseProbe


class FakeDatabaseProbe(DatabaseProbe):
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class TestGetReadinessUseCase:
    def test_status_is_up_when_database_is_available(self) -> None:
        use_case = GetReadinessUseCase("auth", FakeDatabaseProbe(available=True))

        result = use_case.execute()

        assert result.service == "auth"
        assert result.status is ServiceStatus.UP

    def test_status_is_down_when_database_is_unavailable(self) -> None:
        use_case = GetReadinessUseCase("auth", FakeDatabaseProbe(available=False))

        assert use_case.execute().status is ServiceStatus.DOWN
