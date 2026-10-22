"""Corps HTML des mails : texte échappé, paragraphes, liens http(s) cliquables seulement."""

from app.payment_confirmation.infrastructure.senders.mail_html import MailHtml


class TestMailHtml:
    def test_escapes_markup_and_quotes_so_user_text_never_becomes_html(self) -> None:
        html = MailHtml.from_text("<script>alert('x')</script> & \"fin\"")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html and "&amp;" in html
        assert "&quot;fin&quot;" in html and "&#x27;x&#x27;" in html

    def test_blank_lines_make_paragraphs_and_single_breaks_become_br(self) -> None:
        html = MailHtml.from_text("Bonjour,\n\nLigne un\nLigne deux\n\nL'équipe")

        assert html.count("<p>") == 3
        assert "Ligne un<br>Ligne deux" in html
        assert "<br><br>" not in html

    def test_http_and_https_links_are_clickable(self) -> None:
        html = MailHtml.from_text(
            "Voir https://basecamp.example/suivi?a=1&b=2 puis http://exemple.org."
        )

        assert '<a href="https://basecamp.example/suivi?a=1&amp;b=2">' in html
        assert '<a href="http://exemple.org.">' in html or '<a href="http://exemple.org">' in html

    def test_other_schemes_are_left_as_plain_text(self) -> None:
        html = MailHtml.from_text("javascript:alert(1) data:text/html,<b>x</b> ftp://h/f")

        assert "<a " not in html
        assert "&lt;b&gt;" in html

    def test_a_quote_cannot_break_out_of_the_href(self) -> None:
        html = MailHtml.from_text('https://h.example/"onmouseover="alert(1)')

        assert 'onmouseover="' not in html
        assert html.count("<a ") <= 1

    def test_empty_text_gives_an_empty_document(self) -> None:
        assert MailHtml.from_text("") == ""
