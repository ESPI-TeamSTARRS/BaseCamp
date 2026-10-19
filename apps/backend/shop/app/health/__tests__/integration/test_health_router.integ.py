from httpx import ASGITransport, AsyncClient

from app.main import create_app


class TestHealthRouter:
    async def test_health_endpoint_returns_up(self) -> None:
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "up"
