from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.business_event import BusinessEvent
from app.observability.domain.value_objects.event_key import EventKey
from app.observability.infrastructure.metrics.counting_event_logger import CountingEventLogger
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)


class Setup:
    def __init__(self) -> None:
        self.journal = InMemoryBusinessEventLogger()
        self.metrics = InProcessRequestMetrics()
        self.logger = CountingEventLogger(self.journal, self.metrics, {"shop", "billing"})

    def counted(self) -> dict[EventKey, int]:
        return dict(self.metrics.snapshot().events)


class TestCounting:
    def test_an_event_is_written_to_the_journal_then_counted(self) -> None:
        setup = Setup()
        event = BusinessEvent.success("auth.login_succeeded", attributes={"step": "password"})

        setup.logger.log(event)
        setup.logger.log(event)

        assert setup.journal.events == [event, event]
        assert setup.counted() == {EventKey("auth.login_succeeded", "success", "", ""): 2}

    def test_the_cause_and_the_step_are_the_detail_of_their_events(self) -> None:
        setup = Setup()

        setup.logger.log(
            BusinessEvent.denied(
                "auth.login_failed", "invalid_credentials", attributes={"cause": "wrong_password"}
            )
        )
        setup.logger.log(
            BusinessEvent.denied(
                "auth.lockout_triggered", "too_many_failures", attributes={"step": "password"}
            )
        )

        assert setup.counted() == {
            EventKey("auth.login_failed", "denied", "invalid_credentials", "wrong_password"): 1,
            EventKey("auth.lockout_triggered", "denied", "too_many_failures", "password"): 1,
        }

    def test_a_service_client_is_a_label_only_when_it_is_known(self) -> None:
        setup = Setup()

        for client in ("shop", "billing", "intrus", "a" * 64, None):
            setup.logger.log(
                BusinessEvent.denied(
                    "auth.service_token_denied",
                    "invalid_client",
                    resource_type="service_client",
                    resource_id=client,
                )
            )

        details = {key.detail: count for key, count in setup.counted().items()}
        assert details == {"shop": 1, "billing": 1, "unknown": 3}

    def test_rate_limited_clients_follow_the_same_rule(self) -> None:
        setup = Setup()

        setup.logger.log(
            BusinessEvent.denied(
                "auth.service_rate_limited",
                "rate_limit_exceeded",
                resource_type="service_client",
                resource_id="shop",
            )
        )

        assert list(setup.counted()) == [
            EventKey("auth.service_rate_limited", "denied", "rate_limit_exceeded", "shop")
        ]

    def test_an_attribute_that_is_not_a_closed_code_is_never_a_label(self) -> None:
        setup = Setup()

        setup.logger.log(
            BusinessEvent.denied(
                "auth.login_failed", "invalid_credentials", attributes={"cause": 42}
            )
        )
        setup.logger.log(
            BusinessEvent.denied(
                "auth.token_rejected", "invalid", attributes={"cause": "camille@example.test"}
            )
        )

        assert {key.detail for key in setup.counted()} == {""}
