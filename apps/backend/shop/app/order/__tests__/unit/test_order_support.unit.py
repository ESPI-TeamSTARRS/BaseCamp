import re

from app.order.domain.enums.shipping_country import ShippingCountry
from app.order.domain.services.order_number_generator import OrderNumberGenerator


class TestShippingCountry:
    def test_lists_exactly_the_seven_supported_countries(self) -> None:
        assert {c.value for c in ShippingCountry} == {"FR", "BE", "CH", "LU", "DE", "ES", "IT"}

    def test_parses_case_insensitively_and_refuses_the_others(self) -> None:
        assert ShippingCountry.parse(" fr ") is ShippingCountry.FR
        assert ShippingCountry.parse("US") is None
        assert ShippingCountry.parse("") is None


class TestOrderNumberGenerator:
    def test_numbers_have_a_readable_stable_format_and_are_unique(self) -> None:
        numbers = {OrderNumberGenerator.generate() for _ in range(200)}

        assert len(numbers) == 200
        assert all(re.fullmatch(r"BC-[A-Z0-9]{10}", number) for number in numbers)
