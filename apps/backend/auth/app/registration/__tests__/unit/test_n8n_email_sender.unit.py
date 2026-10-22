import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.email_sender_factory import EmailSenderFactory
from app.registration.infrastructure.clients.mail_html import MailHtml
from app.registration.infrastructure.clients.n8n_email_sender import N8nEmailSender
from app.registration.infrastructure.clients.smtp_email_sender import SmtpEmailSender

URL = "https://flux.example.test/webhook/send-email"
SHARED = "valeur-de-test-du-secret-n8n"
TO = EmailAddress.of("camille.martin@example.org")
LINK = "https://basecamp.example.test/compte/verification#token=jeton-a-usage-unique"
BODY = f"Bonjour,\n\nOuvrez ce lien :\n\n{LINK}\n"


def _sender(transport: httpx.MockTransport, secret: str = SHARED, url: str = URL) -> N8nEmailSender:
    return N8nEmailSender(httpx.Client(transport=transport), url, secret, timeout_seconds=2.0)


def _answering(status: int, body: object = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


def _raising(error: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handler)


class TestRequest:
    def test_it_posts_to_json_with_the_secret_header_and_an_html_body(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"ok": True})

        _sender(httpx.MockTransport(handler)).send(TO, "Confirmez votre adresse", BODY)

        (request,) = seen
        assert (request.method, str(request.url)) == ("POST", URL)
        assert request.headers["X-Mail-Secret"] == SHARED
        assert request.headers["content-type"] == "application/json"
        payload = json.loads(request.content)
        assert set(payload) == {"to", "subject", "body"}
        assert payload["to"] == "camille.martin@example.org"
        assert payload["subject"] == "Confirmez votre adresse"
        assert f'<a href="{LINK}">{LINK}</a>' in payload["body"]

    def test_the_secret_never_travels_in_the_body_or_the_url(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"ok": True})

        _sender(httpx.MockTransport(handler)).send(TO, "Sujet", BODY)

        assert SHARED not in seen[0].content.decode() and SHARED not in str(seen[0].url)

    def test_a_redirect_is_not_followed_so_the_secret_never_goes_elsewhere(self) -> None:
        hosts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return httpx.Response(302, headers={"location": "https://evil.example.test/steal"})

        with pytest.raises(MailDeliveryError) as raised:
            _sender(httpx.MockTransport(handler)).send(TO, "Sujet", BODY)

        assert hosts == ["flux.example.test"]
        assert raised.value.cause == "http_302"


class TestFailures:
    @pytest.mark.parametrize(
        ("transport", "cause"),
        [
            (_answering(403, {"message": "Forbidden"}), "http_403"),
            (_answering(401), "http_401"),
            (_answering(404), "http_404"),
            (_answering(500), "http_500"),
            (_raising(httpx.ReadTimeout("lent")), "timeout"),
            (_raising(httpx.ConnectError("refuse")), "connection_error"),
            (_answering(200, {"ok": False}), "invalid_response"),
            (_answering(200, {"message": "autre chose"}), "invalid_response"),
            (_answering(200, ["ok"]), "invalid_response"),
            (
                httpx.MockTransport(lambda r: httpx.Response(200, text="pas du json")),
                "invalid_response",
            ),
        ],
    )
    def test_every_failure_is_a_delivery_error_with_a_closed_cause(
        self, transport: httpx.MockTransport, cause: str
    ) -> None:
        with pytest.raises(MailDeliveryError) as raised:
            _sender(transport).send(TO, "Sujet", BODY)

        assert raised.value.cause == cause
        assert raised.value.code == "mail_delivery_failed"

    @pytest.mark.parametrize(("url", "secret"), [("", SHARED), (URL, ""), ("", "")])
    def test_without_url_or_secret_nothing_is_sent(self, url: str, secret: str) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"ok": True})

        with pytest.raises(MailDeliveryError) as raised:
            _sender(httpx.MockTransport(handler), secret, url).send(TO, "Sujet", BODY)

        assert raised.value.cause == "not_configured" and calls == []

    def test_a_failure_never_carries_the_address_the_link_or_the_secret(self) -> None:
        with pytest.raises(MailDeliveryError) as raised:
            _sender(_answering(403, {"message": "Forbidden"})).send(TO, "Sujet", BODY)

        text = repr(raised.value) + str(raised.value) + repr(raised.value.__dict__)
        for forbidden in (SHARED, "camille.martin", "jeton-a-usage-unique", URL):
            assert forbidden not in text
        assert raised.value.__cause__ is None


class TestMailHtml:
    def test_text_is_escaped_so_markup_is_never_injected(self) -> None:
        result = MailHtml.from_text('<script>alert("x")</script> & plus')

        assert "<script>" not in result
        assert "&lt;script&gt;" in result and "&amp;" in result

    def test_paragraphs_and_line_breaks_are_kept(self) -> None:
        assert MailHtml.from_text("un\n\ndeux\nligne") == "<p>un</p><p>deux<br>ligne</p>"

    def test_only_http_links_become_clickable_and_stay_escaped(self) -> None:
        result = MailHtml.from_text("voir https://a.example/x?y=1&z=2 et javascript:alert(1)")

        assert (
            '<a href="https://a.example/x?y=1&amp;z=2">https://a.example/x?y=1&amp;z=2</a>'
            in result
        )
        assert '<a href="javascript' not in result


class TestFactory:
    def test_smtp_is_the_default_transport(self) -> None:
        assert isinstance(EmailSenderFactory.build(Settings()), SmtpEmailSender)

    def test_n8n_is_chosen_by_the_setting(self) -> None:
        settings = Settings(
            mail_transport="n8n", n8n_mail_url=URL, n8n_mail_secret=SecretStr(SHARED)
        )

        assert isinstance(EmailSenderFactory.build(settings), N8nEmailSender)


class TestSettings:
    def test_n8n_needs_an_url_and_a_secret(self) -> None:
        for url, secret in (("", ""), (URL, ""), ("", SHARED)):
            with pytest.raises(ValueError, match="APP_N8N_MAIL_URL and APP_N8N_MAIL_SECRET"):
                Settings(mail_transport="n8n", n8n_mail_url=url, n8n_mail_secret=SecretStr(secret))

    def test_smtp_needs_nothing_from_n8n(self) -> None:
        assert Settings(mail_transport="smtp").mail_transport == "smtp"

    def test_the_secret_is_never_shown_in_the_settings_representation(self) -> None:
        settings = Settings(
            mail_transport="n8n", n8n_mail_url=URL, n8n_mail_secret=SecretStr(SHARED)
        )

        assert SHARED not in repr(settings) and SHARED not in str(settings)

    def test_the_timeout_defaults_to_five_seconds_and_must_be_positive(self) -> None:
        assert Settings().n8n_mail_timeout_seconds == 5.0
        with pytest.raises(ValueError, match="greater than 0"):
            Settings(n8n_mail_timeout_seconds=0)
