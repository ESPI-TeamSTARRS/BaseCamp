from httpx import ASGITransport, AsyncClient

from app.health.application.get_readiness import GetReadinessUseCase
from app.health.domain.interfaces.database_probe import DatabaseProbe
from app.main import create_app


class FakeDatabaseProbe(DatabaseProbe):
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


async def _get(path: str, available: bool) -> tuple[int, dict[str, str]]:
    application = create_app()
    application.state.readiness_use_case = GetReadinessUseCase("auth", FakeDatabaseProbe(available))
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


class TestReadinessRouter:
    async def test_ready_returns_200_when_database_is_up(self) -> None:
        status_code, body = await _get("/health/ready", available=True)

        assert status_code == 200
        assert body["status"] == "up"

    async def test_ready_returns_503_when_database_is_down(self) -> None:
        status_code, body = await _get("/health/ready", available=False)

        assert status_code == 503
        assert body["status"] == "down"

    async def test_liveness_stays_200_when_database_is_down(self) -> None:
        status_code, body = await _get("/health", available=False)

        assert status_code == 200
        assert body["status"] == "up"
