import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.backoffice.application.backoffice_errors import FaceImageInvalidError
from app.backoffice.application.complete_operator_invitation import (
    CompleteOperatorInvitationUseCase,
)
from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase
from app.backoffice.presentation.dependencies import (
    get_complete_operator_invitation_use_case,
    get_identify_operator_use_case,
    get_verify_face_use_case,
    get_verify_operator_password_use_case,
)
from app.backoffice.presentation.schemas.face_request import FaceRequest
from app.backoffice.presentation.schemas.face_response import FaceResponse
from app.backoffice.presentation.schemas.identify_request import IdentifyRequest
from app.backoffice.presentation.schemas.identify_response import IdentifyResponse
from app.backoffice.presentation.schemas.invitation_complete_request import (
    InvitationCompleteRequest,
)
from app.backoffice.presentation.schemas.invitation_complete_response import (
    InvitationCompleteResponse,
)
from app.backoffice.presentation.schemas.password_request import PasswordRequest
from app.login.presentation.dependencies import client_ip
from app.login.presentation.schemas.login_response import LoginResponse

router = APIRouter(prefix="/backoffice", tags=["backoffice"])

NO_STORE = "no-store"


@router.post("/identify", response_model=IdentifyResponse)
def identify(
    body: IdentifyRequest,
    request: Request,
    response: Response,
    use_case: Annotated[IdentifyOperatorUseCase, Depends(get_identify_operator_use_case)],
) -> IdentifyResponse:
    """Toujours 200 avec un defi, que le compte existe ou non."""
    identified = use_case.execute(body.email, client_ip(request))
    response.headers["Cache-Control"] = NO_STORE
    return IdentifyResponse(challenge_id=identified.challenge_id, expires_in=identified.expires_in)


@router.post("/face", response_model=FaceResponse)
def face(
    body: FaceRequest,
    request: Request,
    response: Response,
    use_case: Annotated[VerifyFaceUseCase, Depends(get_verify_face_use_case)],
) -> FaceResponse:
    """Visage accepte : 200. Refuse, defi inconnu ou verrouille : meme 401 generique."""
    use_case.execute(body.challenge_id, _decode(body.images), client_ip(request))
    response.headers["Cache-Control"] = NO_STORE
    return FaceResponse()


@router.post("/password", response_model=LoginResponse)
def password(
    body: PasswordRequest,
    request: Request,
    response: Response,
    use_case: Annotated[
        VerifyOperatorPasswordUseCase, Depends(get_verify_operator_password_use_case)
    ],
) -> LoginResponse:
    """Jetons `operator` + `amr` seulement apres le visage; sinon le meme 401 generique."""
    session = use_case.execute(
        body.challenge_id, body.password.get_secret_value(), client_ip(request)
    )
    response.headers["Cache-Control"] = NO_STORE
    return LoginResponse(access_token=session.access_token, expires_in=session.expires_in)


@router.post("/invitation/complete", response_model=InvitationCompleteResponse, status_code=201)
def complete_invitation(
    body: InvitationCompleteRequest,
    request: Request,
    response: Response,
    use_case: Annotated[
        CompleteOperatorInvitationUseCase, Depends(get_complete_operator_invitation_use_case)
    ],
) -> InvitationCompleteResponse:
    """Cree le compte operateur de la personne invitee (mot de passe et visage) : 201.

    Jeton inconnu, expire, revoque, utilise ou adresse bloquee : meme 401 generique. Mot de passe
    faible ou photos refusees : 422, rien n'est consomme.
    """
    use_case.execute(
        body.token.get_secret_value(),
        body.password.get_secret_value(),
        _decode(body.images),
        client_ip(request),
    )
    response.headers["Cache-Control"] = NO_STORE
    return InvitationCompleteResponse()


def _decode(images: list[str]) -> list[bytes]:
    """Base64 strict : tout autre contenu est une image invalide (422), jamais un echec compte."""
    try:
        return [base64.b64decode(image, validate=True) for image in images]
    except (binascii.Error, ValueError):
        raise FaceImageInvalidError from None
