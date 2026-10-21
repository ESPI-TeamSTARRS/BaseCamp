import urllib.request
from email.message import Message


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse de suivre les redirections : la signature ne part jamais ailleurs que vers l'URL configurée."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None
