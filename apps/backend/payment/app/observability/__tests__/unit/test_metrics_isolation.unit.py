"""/metrics n'est jamais routé par la passerelle : garde-fou statique sur la configuration.

La preuve sur la pile (requêtes réelles via Traefik) est dans tests/e2e/scenarios.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[7]
GATEWAY = (REPO_ROOT / "infra/traefik/dynamic.yml").read_text(encoding="utf-8")
COMPOSE = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(?P<body>(?:    .*\n|\n)+)", COMPOSE, re.MULTILINE)
    assert match, f"service {name} introuvable dans docker-compose.yml"
    return match.group("body")


def _active_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


class TestGatewayDoesNotRoutePayment:
    def test_no_traefik_router_or_service_points_to_payment(self) -> None:
        active = "\n".join(_active_lines(GATEWAY))

        # La passerelle exclut `/api/auth/metrics` du routeur auth : une exclusion, pas une route.
        routed = active.replace("!PathPrefix(`/api/auth/metrics`)", "")

        assert "payment" not in active
        assert "/metrics" not in routed

    def test_payment_is_not_on_the_network_traefik_uses(self) -> None:
        networks = re.search(r"networks: \[(.*?)\]", _service_block("payment"))

        assert networks
        listed = {name.strip() for name in networks.group(1).split(",")}
        assert listed == {"payment-net", "payment-data"}
        assert "app" not in listed
        assert "edge" not in listed

    def test_payment_publishes_no_port_and_has_no_traefik_label(self) -> None:
        for service in ("payment", "payment-worker"):
            block = "\n".join(_active_lines(_service_block(service)))
            assert "ports:" not in block
            assert "traefik" not in block

    def test_the_internal_network_is_closed_to_the_host(self) -> None:
        match = re.search(r"^  payment-net:\n    internal: true", COMPOSE, re.MULTILINE)

        assert match
