from dataclasses import replace

import pytest

from app.catalog.__tests__.product_factory import make_product
from app.catalog.domain.enums.availability import Availability


class TestProductAvailability:
    @pytest.mark.parametrize(
        ("stock", "expected"),
        [
            (0, Availability.OUT_OF_STOCK),
            (1, Availability.LOW_STOCK),
            (5, Availability.LOW_STOCK),
            (6, Availability.IN_STOCK),
            (100, Availability.IN_STOCK),
        ],
    )
    def test_availability_depends_on_stock(self, stock: int, expected: Availability) -> None:
        assert make_product(stock=stock).availability is expected


class TestProductInvariants:
    def test_rejects_a_negative_price_but_accepts_zero(self) -> None:
        with pytest.raises(ValueError):
            make_product(price_cents=-1)
        assert make_product(price_cents=0).price_cents == 0

    def test_rejects_negative_stock(self) -> None:
        with pytest.raises(ValueError):
            make_product(stock=-1)

    def test_rejects_blank_name(self) -> None:
        with pytest.raises(ValueError):
            replace(make_product(), name="  ")

    def test_rejects_rating_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            replace(make_product(), rating_value=5.5)

    def test_thumbnail_key_is_the_first_image(self) -> None:
        assert make_product(slug="abc").thumbnail_key == "abc-1.svg"

    def test_thumbnail_key_is_none_without_image(self) -> None:
        assert replace(make_product(), image_keys=()).thumbnail_key is None
