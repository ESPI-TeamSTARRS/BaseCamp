import html
import re

_LINK = re.compile(r"https?://(?:(?!&quot;|&#x27;|&lt;|&gt;)\S)+")


class MailHtml:
    """Texte -> HTML d'un mail : tout est échappé, seuls les liens http(s) deviennent cliquables."""

    @staticmethod
    def from_text(text: str) -> str:
        paragraphs = [block for block in text.strip().split("\n\n") if block.strip()]
        return "".join(f"<p>{MailHtml._inline(block.strip())}</p>" for block in paragraphs)

    @staticmethod
    def _inline(block: str) -> str:
        escaped = html.escape(block)
        linked = _LINK.sub(
            lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>', escaped
        )
        return linked.replace("\n", "<br>")
