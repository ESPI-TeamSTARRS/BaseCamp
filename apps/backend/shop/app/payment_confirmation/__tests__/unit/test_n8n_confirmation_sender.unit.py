"""Adaptateur n8n : contrat du webhook (corps, en-tête secret), refus, délai, réponse invalide."""

import json

import httpx
import pytest

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.mail_line import MailLine
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.infrastructure.senders.n8n_confirmation_sender import (
    N8nConfirmationSender,
)

URL = "https://flux.example.test/webhook/send-email"
SHARED_VALUE = "valeur-de-test-du-secret-n8n"
MAIL = ConfirmationMail(
    to="camille.martin@example.org",
    order_number="BC-ABCDEFGHJK",
    total_cents=4490,
    lines=(MailLine("Popote <b>en titane</b>", 1, 3900), MailLine("Gourde & co", 2, 590)),
)


def _sender(
    handler: httpx.MockTransport, secret: str = SHARED_VALUE, url: str = URL
) -> N8nConfirmationSender:
    return N8nConfirmationSender(httpx.Client(transport=handler), url, secret, timeout_seconds=5.0)


def _reason(sender: N8nConfirmationSender) -> str:
    with pytest.raises(ConfirmationDeliveryError) as error:
        sender.send(MAIL)
    return error.value.reason


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


class TestRequestContract:
    def test_posts_json_to_the_webhook_with_the_secret_header(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        _sender(httpx.MockTransport(handler)).send(MAIL)

        (request,) = seen
        assert (request.method, str(request.url)) == ("POST", URL)
        assert request.headers["x-mail-secret"] == SHARED_VALUE
        assert request.headers["content-type"].startswith("application/json")
        body = json.loads(request.content)
        assert set(body) == {"to", "subject", "body"}
        assert body["to"] == "camille.martin@example.org"
        assert "BC-ABCDEFGHJK" in body["subject"]

    def test_the_body_is_html_with_every_value_escaped(self) -> None:
        seen: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return _ok(request)

        _sender(httpx.MockTransport(handler)).send(MAIL)

        html = seen[0]["body"]
        assert "<p>" in html and "BC-ABCDEFGHJK" in html and "44,90 EUR" in html
        assert "<b>en titane</b>" not in html and "&lt;b&gt;en titane&lt;/b&gt;" in html
        assert "Gourde &amp; co" in html

    def test_the_secret_never_travels_in_the_body_or_the_url(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        _sender(httpx.MockTransport(handler)).send(MAIL)

        assert SHARED_VALUE not in seen[0].content.decode() and SHARED_VALUE not in str(seen[0].url)


class TestFailures:
    @pytest.mark.parametrize("status", [401, 403, 404, 500, 502])
    def test_a_refusal_or_an_outage_is_a_delivery_error_with_its_status(self, status: int) -> None:
        sender = _sender(httpx.MockTransport(lambda r: httpx.Response(status, json={"ok": False})))

        assert _reason(sender) == f"http_{status}"

    def test_a_redirect_is_not_followed_and_is_a_failure(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(302, headers={"location": "https://autre.example/"})

        assert _reason(_sender(httpx.MockTransport(handler))) == "http_302"
        assert len(calls) == 1  # le secret n'est jamais renvoyé ailleurs

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, content=b"pas du json"),
            httpx.Response(200, json={}),
            httpx.Response(200, json={"ok": False}),
            httpx.Response(200, json={"ok": "true"}),
            httpx.Response(200, json=[True]),
            httpx.Response(204),
        ],
    )
    def test_a_reply_without_ok_true_is_an_invalid_response(self, response: httpx.Response) -> None:
        assert _reason(_sender(httpx.MockTransport(lambda r: response))) == "invalid_response"

    def test_a_timeout_and_an_unreachable_server_have_their_own_reasons(self) -> None:
        def slow(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("trop long", request=request)

        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refusé", request=request)

        assert _reason(_sender(httpx.MockTransport(slow))) == "timeout"
        assert _reason(_sender(httpx.MockTransport(down))) == "connection_error"

    @pytest.mark.parametrize(("secret", "url"), [("", URL), (SHARED_VALUE, ""), ("", "")])
    def test_without_the_url_or_the_secret_nothing_is_sent(self, secret: str, url: str) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return _ok(request)

        assert _reason(_sender(httpx.MockTransport(handler), secret, url)) == "not_configured"
        assert calls == []
