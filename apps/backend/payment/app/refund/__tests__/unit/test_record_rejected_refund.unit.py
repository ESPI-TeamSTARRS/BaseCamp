from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.refund.application import refund_event_names as names
from app.refund.application.record_rejected_refund import RecordRejectedRefundUseCase

INTENT_ID = "7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42"


class TestRecordRejectedRefund:
    def test_an_invalid_request_is_logged_with_the_resource_when_the_id_is_a_uuid(self) -> None:
        logger = InMemoryBusinessEventLogger()

        RecordRejectedRefundUseCase(logger).execute(INTENT_ID)

        (event,) = logger.events
        assert (event.event, event.outcome, event.reason) == (
            names.REFUND_REJECTED,
            Outcome.DENIED,
            "invalid_request",
        )
        assert (event.resource_type, event.resource_id) == ("payment_intent", INTENT_ID)
        assert event.attributes == {}

    def test_a_malformed_identifier_is_never_echoed(self) -> None:
        logger = InMemoryBusinessEventLogger()

        RecordRejectedRefundUseCase(logger).execute("4242424242424242")

        (event,) = logger.events
        assert event.resource_id is None
        assert "4242" not in repr(event)
