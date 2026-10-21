import pytest

from app.lockout.domain.entities.truncated_address import truncate_address


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("203.0.113.77", "203.0.113.0/24"),
        ("10.1.2.3", "10.1.2.0/24"),
        ("2001:db8:1234:5678::1", "2001:db8:1234::/48"),
        ("::1", "::/48"),
        ("::ffff:203.0.113.77", "203.0.113.0/24"),
    ],
)
def test_an_address_is_truncated_to_its_network(address: str, expected: str) -> None:
    assert truncate_address(address) == expected


@pytest.mark.parametrize("bad", [None, "", " ", "unknown", "999.1.1.1", "1.2.3", "a:b:c"])
def test_nothing_usable_gives_none(bad: str | None) -> None:
    assert truncate_address(bad) is None
