import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order_tracking.__tests__.fakes import (
    EMAIL,
    NUMBER,
    FakeTrackedOrderReader,
    tracked_order,
)
from app.order_tracking.application.lookup_order import LookupOrderUseCase
from app.order_tracking.application.order_lookup_failed_error import OrderLookupFailedError


def _use_case(
    reader: FakeTrackedOrderReader | None = None,
) -> tuple[LookupOrderUseCase, InMemoryBusinessEventLogger]:
    events = InMemoryBusinessEventLogger()
    reader = reader or FakeTrackedOrderReader(tracked_order())
    return LookupOrderUseCase(reader, events, FakePseudonymizer()), events


class TestLookupOrder:
    def test_returns_status_lines_and_total_for_a_matching_number_and_email(self) -> None:
        use_case, _ = _use_case()

        order = use_case.execute(NUMBER, EMAIL)

        assert (order.number, order.status, order.total_cents) == (NUMBER, "pending_payment", 7800)
        assert [(line.name, line.quantity) for line in order.lines] == [("Popote", 2)]

    @pytest.mark.parametrize("email", [EMAIL.upper(), f"  {EMAIL}  ", "Camille.Martin@Example.org"])
    def test_the_email_is_compared_without_case_or_surrounding_spaces(self, email: str) -> None:
        use_case, _ = _use_case()

        assert use_case.execute(NUMBER, email).number == NUMBER

    def test_a_wrong_email_and_an_unknown_number_fail_with_the_same_error(self) -> None:
        use_case, _ = _use_case()

        with pytest.raises(OrderLookupFailedError) as wrong_email:
            use_case.execute(NUMBER, "intrus@example.org")
        with pytest.raises(OrderLookupFailedError) as unknown:
            use_case.execute("BC-ZZZZZZZZZZ", EMAIL)

        assert type(wrong_email.value) is type(unknown.value)
        assert wrong_email.value.message == unknown.value.message == "Commande introuvable."
        assert vars(wrong_email.value) == vars(unknown.value)

    def test_a_paid_or_expired_status_is_reported_as_is(self) -> None:
        for status in ("paid", "expired"):
            use_case, _ = _use_case(FakeTrackedOrderReader(tracked_order(status)))

            assert use_case.execute(NUMBER, EMAIL).status == status

    def test_emits_order_looked_up_on_success(self) -> None:
        use_case, events = _use_case()

        use_case.execute(NUMBER, EMAIL)

        (event,) = events.events
        assert (event.event, event.outcome) == ("order.looked_up", Outcome.SUCCESS)
        assert (event.resource_type, event.resource_id) == ("order", NUMBER)
        assert event.attributes == {"status": "pending_payment"}

    def test_logs_tell_a_wrong_email_from_an_unknown_number_but_never_the_email(self) -> None:
        use_case, events = _use_case()

        for number, email in ((NUMBER, "intrus@example.org"), ("BC-ZZZZZZZZZZ", EMAIL)):
            with pytest.raises(OrderLookupFailedError):
                use_case.execute(number, email)

        mismatch, unknown = events.events
        assert (mismatch.outcome, mismatch.reason) == (Outcome.DENIED, "email_mismatch")
        assert (unknown.outcome, unknown.reason) == (Outcome.DENIED, "order_not_found")
        assert mismatch.resource_id == NUMBER
        assert unknown.resource_id is None  # un numéro inconnu ne devient pas une ressource
        dump = repr(events.events)
        assert "intrus@example.org" not in dump
        assert EMAIL not in dump
        assert all("email_hash" in event.attributes for event in events.events)

    def test_an_unknown_number_is_still_looked_up_once(self) -> None:
        reader = FakeTrackedOrderReader(tracked_order())
        use_case, _ = _use_case(reader)

        with pytest.raises(OrderLookupFailedError):
            use_case.execute("BC-ZZZZZZZZZZ", EMAIL)

        assert reader.lookups == ["BC-ZZZZZZZZZZ"]
