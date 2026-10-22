"""Consultation admin des commandes : lecture seule, événements sans donnée personnelle."""

from uuid import UUID

import pytest

from app.admin_orders.__tests__.fakes import ADDRESS_LINE, EMAIL, StubAdminOrderReader, make_order
from app.admin_orders.application.admin_order_not_found_error import AdminOrderNotFoundError
from app.admin_orders.application.get_admin_order import GetAdminOrderUseCase
from app.admin_orders.application.list_admin_orders import ListAdminOrdersUseCase
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome

OPERATOR = UUID("0b6c1a52-7a3e-4f0e-9b57-3f2d8c6a1e90")


class _Pseudonymizer:
    def pseudonymize(self, value: str) -> str:
        return "pseudo-" + value[:4]


class TestListAdminOrders:
    def test_relays_the_filters_and_the_page_to_the_reader(self) -> None:
        reader = StubAdminOrderReader(make_order())
        use_case = ListAdminOrdersUseCase(reader, InMemoryBusinessEventLogger(), _Pseudonymizer())

        page = use_case.execute(OPERATOR, "paid", "BC-00", 20, 40)

        assert reader.queries == [("paid", "BC-00", 20, 40)]
        assert (page.total, page.limit, page.offset) == (1, 20, 40)

    def test_emits_one_event_without_the_search_text_nor_personal_data(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = ListAdminOrdersUseCase(
            StubAdminOrderReader(make_order()), events, _Pseudonymizer()
        )

        use_case.execute(OPERATOR, "paid", EMAIL, 20, 0)

        (event,) = events.events
        assert (event.event, event.outcome) == ("admin_orders.listed", Outcome.SUCCESS)
        assert (event.resource_type, event.actor_type) == ("order", "user")
        assert event.actor_id == "pseudo-0b6c"
        assert event.attributes == {
            "status": "paid",
            "searched": True,
            "limit": 20,
            "offset": 0,
            "returned": 1,
        }
        assert EMAIL not in repr(event)

    def test_no_filter_means_no_status_and_not_searched(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = ListAdminOrdersUseCase(StubAdminOrderReader(), events, _Pseudonymizer())

        use_case.execute(OPERATOR, None, None, 20, 0)

        assert events.events[0].attributes["status"] is None
        assert events.events[0].attributes["searched"] is False
        assert events.events[0].attributes["returned"] == 0


class TestGetAdminOrder:
    def test_returns_the_order_and_emits_a_pseudonymised_view_event(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = GetAdminOrderUseCase(
            StubAdminOrderReader(make_order("o-9")), events, _Pseudonymizer()
        )

        order = use_case.execute(OPERATOR, "o-9")

        assert order.id == "o-9"
        (event,) = events.events
        assert (event.event, event.outcome) == ("admin_orders.viewed", Outcome.SUCCESS)
        assert (event.resource_type, event.resource_id) == ("order", "o-9")
        assert event.actor_id == "pseudo-0b6c"
        assert EMAIL not in repr(event) and ADDRESS_LINE not in repr(event)

    def test_an_unknown_order_is_denied_with_a_stable_reason(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = GetAdminOrderUseCase(StubAdminOrderReader(), events, _Pseudonymizer())

        with pytest.raises(AdminOrderNotFoundError):
            use_case.execute(OPERATOR, "absente")

        (event,) = events.events
        assert (event.event, event.outcome, event.reason) == (
            "admin_orders.view_denied",
            Outcome.DENIED,
            "order_not_found",
        )
        assert event.resource_id == "absente"
