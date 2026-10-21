import json

import httpx
import pytest

from app.core.logging.correlation import set_correlation_id
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.infrastructure.clients.http_payment_gateway import HttpPaymentGateway

TOKEN = "tok-shop-test-0001"  # noqa: S105
INTENT = {"id": "7d1f", "status": "requires_confirmation", "amount": 4490, "currency": "EUR"}


def _gateway(transport: httpx.MockTransport) -> HttpPaymentGateway:
    return HttpPaymentGateway(
        httpx.Client(base_url="http://payment:8000", transport=transport), TOKEN
    )


def _call(gateway: HttpPaymentGateway) -> PaymentIntentRef:
    return gateway.create_intent("CMD-1", 4490, "EUR", "key-00000001")


def _responding(status: int, body: object = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


def _raising(error: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handler)


class TestHttpPaymentGateway:
    def test_sends_token_idempotency_key_and_the_order_to_payment(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(201, json=INTENT)

        intent = _call(_gateway(httpx.MockTransport(handler)))

        request = seen[0]
        assert (request.method, request.url.path) == ("POST", "/payments/intents")
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Idempotency-Key"] == "key-00000001"
        assert json.loads(request.content) == {
            "order_reference": "CMD-1",
            "amount": 4490,
            "currency": "EUR",
        }
        assert (intent.id, intent.status, intent.amount_cents) == (
            "7d1f",
            "requires_confirmation",
            4490,
        )

    def test_a_replay_answered_200_is_accepted(self) -> None:
        assert _call(_gateway(_responding(200, INTENT))).id == "7d1f"

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 401])
    def test_overload_outage_and_misconfiguration_mean_unavailable(self, status: int) -> None:
        with pytest.raises(PaymentUnavailableError):
            _call(_gateway(_responding(status, {"detail": "x"})))

    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError("no route"),
            httpx.ConnectTimeout("slow"),
            httpx.ReadTimeout("slow"),
            httpx.PoolTimeout("busy"),
        ],
    )
    def test_network_failures_and_timeouts_mean_unavailable(self, error: Exception) -> None:
        with pytest.raises(PaymentUnavailableError):
            _call(_gateway(_raising(error)))

    def test_an_unreadable_answer_means_unavailable(self) -> None:
        with pytest.raises(PaymentUnavailableError):
            _call(_gateway(httpx.MockTransport(lambda r: httpx.Response(201, text="<html>"))))

    @pytest.mark.parametrize(("status", "conflict"), [(409, True), (422, False)])
    def test_business_refusals_are_not_outages(self, status: int, conflict: bool) -> None:
        with pytest.raises(PaymentRejectedError) as error:
            _call(_gateway(_responding(status, {"detail": "x"})))

        assert error.value.conflict is conflict

    def test_the_failure_never_carries_the_token_or_the_cause(self) -> None:
        with pytest.raises(PaymentUnavailableError) as error:
            _call(_gateway(_raising(httpx.ConnectError(f"boom {TOKEN}"))))

        assert TOKEN not in str(error.value)
        assert error.value.__cause__ is None


class TestCorrelation:
    def test_the_correlation_id_of_the_request_is_forwarded_to_payment(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(201, json=INTENT)

        set_correlation_id("corr-0123456789")
        _call(_gateway(httpx.MockTransport(handler)))

        assert seen[0].headers["X-Correlation-ID"] == "corr-0123456789"


class TestReadAndConfirm:
    def test_reads_an_intent_by_identifier(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=INTENT)

        intent = _gateway(httpx.MockTransport(handler)).get_intent("7d1f")

        assert (seen[0].method, seen[0].url.path) == ("GET", "/payments/intents/7d1f")
        assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
        assert intent.status == "requires_confirmation"

    def test_confirms_with_a_test_method_and_an_idempotency_key(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={**INTENT, "status": "succeeded"})

        intent = _gateway(httpx.MockTransport(handler)).confirm_intent(
            "7d1f", "pm_test_success", "confirm-00000001"
        )

        request = seen[0]
        assert (request.method, request.url.path) == ("POST", "/payments/intents/7d1f/confirm")
        assert request.headers["Idempotency-Key"] == "confirm-00000001"
        assert json.loads(request.content) == {"payment_method": "pm_test_success"}
        assert intent.status == "succeeded"

    def test_the_identifier_cannot_escape_the_path(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=INTENT)

        _gateway(httpx.MockTransport(handler)).get_intent("../admin")

        assert seen[0].url.raw_path == b"/payments/intents/..%2Fadmin"

    @pytest.mark.parametrize(("status", "conflict"), [(404, False), (409, True), (422, False)])
    def test_business_refusals_become_a_rejection(self, status: int, conflict: bool) -> None:
        with pytest.raises(PaymentRejectedError) as error:
            _gateway(_responding(status, {"detail": "x"})).get_intent("7d1f")

        assert error.value.conflict is conflict

    @pytest.mark.parametrize("status", [401, 429, 500, 503])
    def test_technical_failures_become_unavailable(self, status: int) -> None:
        with pytest.raises(PaymentUnavailableError):
            _gateway(_responding(status, {})).confirm_intent("7d1f", "pm_test_success", "k-0000001")
