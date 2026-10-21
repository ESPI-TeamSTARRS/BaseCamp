"""`/metrics` n'est jamais route par la passerelle : garde-fou statique sur la configuration.

`auth` est joint par Traefik (`/api/auth`) : le prefixe retire, `/api/auth/metrics` atteindrait
`/metrics`. La passerelle l'exclut donc du routeur `auth`, en developpement comme en production.
La preuve sur la pile (requetes reelles via Traefik) est dans tests/e2e/scenarios.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[7]
GATEWAYS = ("infra/traefik/dynamic.yml", "deploy/traefik/dynamic.prod.yml")


def _active(path: str) -> list[str]:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


@pytest.mark.parametrize("gateway", GATEWAYS)
class TestGatewayDoesNotRouteMetrics:
    def test_the_auth_router_excludes_the_metrics_prefix(self, gateway: str) -> None:
        rules = [line for line in _active(gateway) if 'rule: "PathPrefix(`/api/auth`)' in line]

        assert len(rules) == 1
        assert "!PathPrefix(`/api/auth/metrics`)" in rules[0]
        assert "!PathPrefix(`/api/auth/internal`)" in rules[0]

    def test_no_other_router_points_at_metrics(self, gateway: str) -> None:
        positive = [line for line in _active(gateway) if "rule:" in line and "/metrics" in line]

        assert all("!PathPrefix(`/api/auth/metrics`)" in line for line in positive)
        assert not [line for line in _active(gateway) if "Path(`/metrics`)" in line]
