from datetime import timedelta

import jwt

from app.login.__tests__.fakes import START, make_account
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.jwt_access_token_verifier import JwtAccessTokenVerifier

ISSUER = "basecamp-auth"
AUDIENCE = "basecamp-client-api"


class TestClaims:
    def test_the_classic_login_never_delivers_operator_nor_amr(self) -> None:
        claims = AccessTokenClaims.issue(make_account(role="operator"), START, 900, "jti")

        assert claims.roles == ()
        assert claims.amr == ()

    def test_a_customer_keeps_their_role(self) -> None:
        claims = AccessTokenClaims.issue(make_account(role="customer"), START, 900, "jti")

        assert claims.roles == ("customer",)

    def test_the_three_step_login_delivers_operator_with_face_and_password(self) -> None:
        claims = AccessTokenClaims.issue_operator(make_account(role="operator"), START, 900, "jti")

        assert claims.roles == ("operator",)
        assert claims.amr == ("face", "pwd")
        assert claims.expires_at - claims.issued_at == timedelta(seconds=900)


class TestSignedToken:
    def _tokens(self) -> tuple[JwtAccessTokenSigner, JwtAccessTokenVerifier]:
        keys = Ed25519KeyRing.generate()
        return (
            JwtAccessTokenSigner(keys, ISSUER, AUDIENCE),
            JwtAccessTokenVerifier(keys, ISSUER, AUDIENCE),
        )

    def test_an_operator_token_carries_the_amr_claim_and_stays_a_client_token(self) -> None:
        signer, _ = self._tokens()
        claims = AccessTokenClaims.issue_operator(make_account(role="operator"), START, 900, "jti")

        payload = jwt.decode(signer.sign(claims), options={"verify_signature": False})

        assert payload["roles"] == ["operator"]
        assert payload["amr"] == ["face", "pwd"]
        assert payload["token_use"] == "client"
        assert payload["aud"] == AUDIENCE

    def test_a_classic_token_has_no_amr_claim(self) -> None:
        signer, _ = self._tokens()
        claims = AccessTokenClaims.issue(make_account(role="customer"), START, 900, "jti")

        payload = jwt.decode(signer.sign(claims), options={"verify_signature": False})

        assert "amr" not in payload

    def test_the_verifier_reads_the_amr_back(self) -> None:
        signer, verifier = self._tokens()
        claims = AccessTokenClaims.issue_operator(make_account(role="operator"), START, 900, "jti")

        verified = verifier.verify(signer.sign(claims), START)

        assert verified.amr == ("face", "pwd")
        assert verified.roles == ("operator",)
