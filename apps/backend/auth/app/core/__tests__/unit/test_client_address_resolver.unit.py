import pytest

from app.core.client_address_resolver import ClientAddressResolver

DOCKER = "172.16.0.0/12"
CLOUDFLARE = "173.245.48.0/20"


def _resolver(*networks: str) -> ClientAddressResolver:
    return ClientAddressResolver.from_cidrs(networks)


class TestWithoutTrustedProxy:
    def test_the_peer_address_is_used_and_every_header_is_ignored(self) -> None:
        resolver = _resolver()

        assert resolver.resolve("203.0.113.5", "198.51.100.9") == "203.0.113.5"

    def test_a_peer_outside_the_trusted_ranges_cannot_forge_the_address(self) -> None:
        resolver = _resolver(DOCKER)

        assert resolver.resolve("203.0.113.5", "10.9.9.9, 198.51.100.9") == "203.0.113.5"

    def test_a_missing_peer_gives_nothing(self) -> None:
        assert _resolver(DOCKER).resolve(None, "198.51.100.9") is None

    @pytest.mark.parametrize("peer", ["", "testclient", "999.1.1.1"])
    def test_an_unreadable_peer_is_never_trusted(self, peer: str) -> None:
        assert _resolver(DOCKER).resolve(peer, "198.51.100.9") == (peer or None)


class TestBehindTrustedProxies:
    def test_the_forwarded_address_is_used_when_the_peer_is_a_trusted_proxy(self) -> None:
        resolver = _resolver(DOCKER)

        assert resolver.resolve("172.18.0.4", "198.51.100.9") == "198.51.100.9"

    def test_trusted_hops_are_skipped_from_the_right(self) -> None:
        resolver = _resolver(DOCKER, CLOUDFLARE)

        chain = "198.51.100.9, 173.245.48.10, 172.18.0.3"

        assert resolver.resolve("172.18.0.4", chain) == "198.51.100.9"

    def test_an_address_forged_by_the_client_on_the_left_is_never_chosen(self) -> None:
        resolver = _resolver(DOCKER, CLOUDFLARE)

        chain = "6.6.6.6, 198.51.100.9, 173.245.48.10"  # le client a pose 6.6.6.6 lui-meme

        assert resolver.resolve("172.18.0.4", chain) == "198.51.100.9"

    def test_two_clients_behind_the_same_proxy_stay_distinct(self) -> None:
        resolver = _resolver(DOCKER)

        first = resolver.resolve("172.18.0.4", "198.51.100.9")
        second = resolver.resolve("172.18.0.4", "198.51.100.10")

        assert first != second

    def test_without_header_the_proxy_address_is_used(self) -> None:
        assert _resolver(DOCKER).resolve("172.18.0.4", None) == "172.18.0.4"
        assert _resolver(DOCKER).resolve("172.18.0.4", "") == "172.18.0.4"

    def test_when_every_hop_is_trusted_the_origin_is_the_leftmost(self) -> None:
        resolver = _resolver(DOCKER)

        assert resolver.resolve("172.18.0.4", "172.19.0.9, 172.18.0.3") == "172.19.0.9"

    def test_unreadable_entries_are_skipped_and_an_unreadable_header_falls_back_to_the_peer(
        self,
    ) -> None:
        resolver = _resolver(DOCKER)

        assert resolver.resolve("172.18.0.4", "198.51.100.9, not-an-ip") == "198.51.100.9"
        assert resolver.resolve("172.18.0.4", "not-an-ip") == "172.18.0.4"

    def test_ipv6_clients_are_supported(self) -> None:
        resolver = _resolver(DOCKER, "2400:cb00::/32")

        assert resolver.resolve("172.18.0.4", "2001:db8::7, 2400:cb00::1") == "2001:db8::7"


class TestConfiguration:
    def test_cidrs_are_parsed_from_a_comma_separated_text(self) -> None:
        resolver = ClientAddressResolver.from_text(" 172.16.0.0/12 , 10.0.0.0/8 ,")

        assert resolver.resolve("10.1.2.3", "198.51.100.9") == "198.51.100.9"

    def test_an_empty_text_trusts_nobody(self) -> None:
        assert ClientAddressResolver.from_text("").resolve("10.1.2.3", "1.2.3.4") == "10.1.2.3"

    def test_a_bad_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="trusted proxies"):
            ClientAddressResolver.from_text("172.16.0.0/12, nope")
