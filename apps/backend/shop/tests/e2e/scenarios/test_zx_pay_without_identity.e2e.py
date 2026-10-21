"""`auth` arrêté : la boutique ne peut plus obtenir de jeton de service pour appeler `payment` (WORK-41).

Sans jeton valide, `/pay` répond un 503 propre et rapide (aucun détail technique), sans bloquer; dès
qu'`auth` revient, le paiement repart seul. Le jeton de la boutique ne vit qu'en mémoire : on
redémarre `shop` pour repartir sans jeton en cache. Le test remet toujours `auth` en marche.
"""

import time
from collections.abc import Iterator

import httpx
import pytest

from app.__tests__.payment_stack import (
    ORDERS_PATH,
    compose,
    needs_docker,
    new_client,
    place_order,
    post,
)

pytestmark = needs_docker

MAX_SECONDS = 10  # un auth arrêté ne doit jamais bloquer la boutique


@pytest.fixture
def client() -> httpx.Client:
    return new_client()


@pytest.fixture
def auth_stopped() -> Iterator[None]:
    compose("stop", "auth")
    try:
        compose("restart", "shop")
        compose("up", "-d", "--wait", "--wait-timeout", "90", "shop")
        yield
    finally:
        compose("up", "-d", "--wait", "--wait-timeout", "120", "auth")


class TestPayWithoutIdentity:
    def test_pay_is_a_clean_503_while_auth_is_down_then_recovers(
        self, client: httpx.Client, auth_stopped: None
    ) -> None:
        order, _ = place_order(client, "zx-no-auth")

        started = time.monotonic()
        response = post(client, f"{ORDERS_PATH}/{order['id']}/pay", None)
        elapsed = time.monotonic() - started

        assert response.status_code == 503
        assert elapsed < MAX_SECONDS
        for leak in ("auth", "token", "Traceback", "http://", "secret"):
            assert leak not in response.text

        compose("up", "-d", "--wait", "--wait-timeout", "120", "auth")
        recovered = post(client, f"{ORDERS_PATH}/{order['id']}/pay", None)

        assert recovered.status_code == 201
