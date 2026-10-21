from typing import cast

from fastapi import Request

from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase


def get_identify_operator_use_case(request: Request) -> IdentifyOperatorUseCase:
    """Les cas d'usage sont cables dans composition.py (la presentation n'importe pas l'infrastructure)."""
    return cast(IdentifyOperatorUseCase, request.app.state.identify_operator_use_case)


def get_verify_face_use_case(request: Request) -> VerifyFaceUseCase:
    return cast(VerifyFaceUseCase, request.app.state.verify_face_use_case)


def get_verify_operator_password_use_case(request: Request) -> VerifyOperatorPasswordUseCase:
    return cast(VerifyOperatorPasswordUseCase, request.app.state.verify_operator_password_use_case)
