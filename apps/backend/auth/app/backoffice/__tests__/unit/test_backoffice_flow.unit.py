from datetime import timedelta

import pytest

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.__tests__.flow import (
    ADDRESS,
    OPERATOR_EMAIL,
    OPERATOR_SECRET,
    TTL,
    WRONG_SECRET,
    Flow,
)
from app.backoffice.application.backoffice_errors import (
    BackofficeRefusedError,
    FaceImageInvalidError,
    FaceTemplateInvalidError,
)
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.core.events.outcome import Outcome


def _to_face_ok(flow: Flow) -> str:
    challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
    flow.face.execute(challenge, [PNG], ADDRESS)
    return challenge


class TestIdentify:
    def test_a_known_operator_gets_a_challenge_with_a_short_life(self) -> None:
        flow = Flow()

        identified = flow.identify.execute(OPERATOR_EMAIL, ADDRESS)

        assert identified.challenge_id == "challenge-1"
        assert identified.expires_in == TTL == 120
        (stored,) = flow.store.challenges.values()
        assert stored.account_id == flow.operator.id
        assert not stored.face_ok

    @pytest.mark.parametrize(
        "email",
        ["inconnu@example.com", "client@example.com", "  OPERATEUR@example.com "],
    )
    def test_an_unknown_or_non_operator_identifier_gets_the_same_kind_of_response(
        self, email: str
    ) -> None:
        flow = Flow()

        identified = flow.identify.execute(email, ADDRESS)

        assert identified.challenge_id.startswith("challenge-")
        assert identified.expires_in == TTL
        assert len(flow.store.challenges) == 1

    def test_unknown_and_known_identifiers_do_the_same_work(self) -> None:
        known, unknown = Flow(), Flow()

        known.identify.execute(OPERATOR_EMAIL, ADDRESS)
        unknown.identify.execute("inconnu@example.com", ADDRESS)

        assert known.store.commits == unknown.store.commits == 1
        assert len(known.store.challenges) == len(unknown.store.challenges) == 1

    def test_a_disabled_operator_gets_a_decoy(self) -> None:
        flow = Flow()
        flow.accounts.accounts[flow.operator.id] = type(flow.operator)(
            flow.operator.id,
            flow.operator.email,
            flow.operator.password_hash,
            "operator",
            True,
            True,
        )

        flow.identify.execute(OPERATOR_EMAIL, ADDRESS)

        (stored,) = flow.store.challenges.values()
        assert stored.decoy

    def test_the_challenge_id_is_never_stored_nor_logged(self) -> None:
        flow = Flow()

        identified = flow.identify.execute(OPERATOR_EMAIL, ADDRESS)

        assert identified.challenge_id not in repr(flow.store.challenges)
        assert identified.challenge_id not in repr(flow.events.events)
        assert identified.challenge_id not in repr(identified)

    def test_expired_challenges_are_purged_on_the_next_identify(self) -> None:
        flow = Flow()
        flow.identify.execute(OPERATOR_EMAIL, ADDRESS)
        flow.tick(TTL + 1)

        flow.identify.execute(OPERATOR_EMAIL, ADDRESS)

        assert len(flow.store.challenges) == 1

    def test_the_event_names_the_step_without_revealing_the_account(self) -> None:
        flow = Flow()

        flow.identify.execute("inconnu@example.com", ADDRESS)

        (event,) = flow.events.events
        assert event.event == "auth.backoffice_identify"
        assert event.outcome is Outcome.SUCCESS
        assert "inconnu@example.com" not in repr(event)
        assert event.attributes["step"] == "identify"


class TestFace:
    def test_an_accepted_face_leaves_a_face_ok_challenge(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        flow.face.execute(challenge, [PNG], ADDRESS)

        (stored,) = flow.store.challenges.values()
        assert stored.face_ok
        face = [e for e in flow.events.events if e.event == "auth.backoffice_face_result"]
        assert face[0].outcome is Outcome.SUCCESS

    def test_one_recognised_image_among_three_is_enough(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        flow.face.execute(challenge, [OTHER_PNG, JPEG, PNG], ADDRESS)

        assert next(iter(flow.store.challenges.values())).face_ok

    def test_a_refused_face_destroys_the_challenge_and_counts(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [OTHER_PNG], ADDRESS)

        assert flow.store.challenges == {}
        assert ("face", "fp-" + _fp(OPERATOR_EMAIL)) in flow.lockouts.rows

    def test_a_challenge_serves_once(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)
        flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS)

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [PNG], ADDRESS)

    @pytest.mark.parametrize("token", ["challenge-99", ""])
    def test_an_unknown_challenge_is_the_generic_error(self, token: str) -> None:
        flow = Flow()

        with pytest.raises(BackofficeRefusedError) as raised:
            flow.face.execute(token or "x", [PNG], ADDRESS)

        assert raised.value.message == "Identifiants invalides."

    def test_an_expired_challenge_is_the_generic_error(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        flow.tick(TTL + 1)

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [PNG], ADDRESS)

    def test_an_unknown_identifier_counts_as_a_refused_face(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute("inconnu@example.com", ADDRESS).challenge_id

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [PNG], ADDRESS)

        assert ("face", "fp-" + _fp("inconnu@example.com")) in flow.lockouts.rows

    def test_an_operator_without_template_is_refused_as_a_wrong_face(self) -> None:
        flow = Flow()
        flow.store.templates.clear()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [PNG], ADDRESS)

    @pytest.mark.parametrize(
        "images",
        [[], [PNG] * 4, [b""], [b"GIF89a" + b"x" * 20], [PNG + b"x" * 1_048_577]],
    )
    def test_images_out_of_limits_are_a_422_and_do_not_count(self, images: list[bytes]) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(FaceImageInvalidError):
            flow.face.execute(challenge, images, ADDRESS)

        assert flow.lockouts.rows == {}
        assert len(flow.store.challenges) == 1  # le defi n'est pas consomme

    def test_an_unreadable_image_does_not_count_and_the_challenge_survives(self) -> None:
        class Unreadable(FakeReconnaissanceFaciale):
            def verifier(self, capture: bytes, gabarit: bytes) -> bool:
                raise ImageInvalide

        flow = Flow(Unreadable())
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(FaceImageInvalidError):
            flow.face.execute(challenge, [PNG], ADDRESS)

        assert flow.lockouts.rows == {}
        assert len(flow.store.challenges) == 1

    def test_an_invalid_template_is_a_409_logged_and_does_not_count(self) -> None:
        class BrokenTemplate(FakeReconnaissanceFaciale):
            def verifier(self, capture: bytes, gabarit: bytes) -> bool:
                raise GabaritInvalide

        flow = Flow(BrokenTemplate())
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(FaceTemplateInvalidError):
            flow.face.execute(challenge, [PNG], ADDRESS)

        assert flow.lockouts.rows == {}
        assert flow.store.challenges == {}
        logged = [e for e in flow.events.events if e.reason == "invalid_template"]
        assert len(logged) == 1
        assert "operateur@example.com" not in repr(logged[0])

    def test_no_image_and_no_score_reach_the_events(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [OTHER_PNG], ADDRESS)

        text = repr(flow.events.events)

        assert "PNG" not in text and "score" not in text and OPERATOR_EMAIL not in text


class TestFaceLockout:
    def test_five_refused_faces_lock_the_step_for_five_minutes(self) -> None:
        flow = Flow()
        for _ in range(5):
            challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
            with pytest.raises(BackofficeRefusedError):
                flow.face.execute(challenge, [OTHER_PNG], ADDRESS)
            flow.tick()

        locked = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(locked, [PNG], ADDRESS)  # le bon visage ne passe plus

        events = [e.event for e in flow.events.events]
        assert "auth.backoffice_lockout" in events
        flow.tick(5 * 60)
        again = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        flow.face.execute(again, [PNG], ADDRESS)  # le blocage est expire

    def test_four_refused_faces_do_not_lock(self) -> None:
        flow = Flow()
        for _ in range(4):
            challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
            with pytest.raises(BackofficeRefusedError):
                flow.face.execute(challenge, [OTHER_PNG], ADDRESS)
            flow.tick()

        _to_face_ok(flow)

    def test_refused_faces_never_count_as_wrong_passwords(self) -> None:
        flow = Flow()
        for _ in range(4):
            challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
            with pytest.raises(BackofficeRefusedError):
                flow.face.execute(challenge, [OTHER_PNG], ADDRESS)
            flow.tick()

        assert not any(scope == "operator_password" for scope, _ in flow.lockouts.rows)

    def test_the_address_counter_is_shared_between_identifiers(self) -> None:
        flow = Flow()
        for index in range(20):
            challenge = flow.identify.execute(f"inconnu{index}@example.com", ADDRESS).challenge_id
            with pytest.raises(BackofficeRefusedError):
                flow.face.execute(challenge, [PNG], ADDRESS)
            flow.tick(1)

        own = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(own, [PNG], ADDRESS)  # l'adresse est bloquee pour tous

        other = flow.identify.execute(OPERATOR_EMAIL, "198.51.100.77").challenge_id
        flow.face.execute(other, [PNG], "198.51.100.77")  # une autre adresse passe


class TestPassword:
    def test_the_full_flow_issues_an_operator_token_with_amr(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)

        session = flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS)

        claims = flow.signer.signed[-1]
        assert session.access_token == f"signed::{flow.operator.id}"
        assert session.expires_in == 900
        assert claims.roles == ("operator",)
        assert claims.amr == ("face", "pwd")
        assert flow.store.challenges == {}  # defi consomme
        assert flow.lockouts.rows == {}  # compteurs remis a zero

    def test_the_password_is_refused_without_a_face_ok_even_when_right(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id

        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS)

        assert flow.signer.signed == []
        assert flow.store.challenges == {}
        assert flow.verifier.decoys == 1 and flow.verifier.verifications == 0

    def test_a_missing_face_is_not_counted_as_a_wrong_password(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, WRONG_SECRET, ADDRESS)

        assert flow.lockouts.rows == {}

    def test_a_wrong_password_destroys_the_challenge_and_counts(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)

        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, WRONG_SECRET, ADDRESS)

        assert flow.store.challenges == {}
        assert ("operator_password", "fp-" + _fp(OPERATOR_EMAIL)) in flow.lockouts.rows

    def test_three_wrong_passwords_lock_the_step_for_five_minutes(self) -> None:
        flow = Flow()
        for _ in range(3):
            challenge = _to_face_ok(flow)
            with pytest.raises(BackofficeRefusedError):
                flow.password.execute(challenge, WRONG_SECRET, ADDRESS)
            flow.tick()

        challenge = _to_face_ok(flow)
        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(
                challenge, OPERATOR_SECRET, ADDRESS
            )  # le bon mot de passe non plus

        assert any(e.event == "auth.backoffice_lockout" for e in flow.events.events)
        flow.tick(timedelta(minutes=5).seconds)
        challenge = _to_face_ok(flow)
        assert flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS).access_token

    def test_two_wrong_passwords_do_not_lock(self) -> None:
        flow = Flow()
        for _ in range(2):
            challenge = _to_face_ok(flow)
            with pytest.raises(BackofficeRefusedError):
                flow.password.execute(challenge, WRONG_SECRET, ADDRESS)
            flow.tick()

        challenge = _to_face_ok(flow)

        assert flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS).access_token

    @pytest.mark.parametrize("token", ["challenge-99", "x"])
    def test_an_unknown_challenge_is_the_generic_error_and_costs_a_verification(
        self, token: str
    ) -> None:
        flow = Flow()

        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(token, OPERATOR_SECRET, ADDRESS)

        assert flow.verifier.decoys == 1

    def test_an_expired_face_ok_challenge_is_refused(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)
        flow.tick(TTL + 1)

        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS)

    def test_a_complete_login_clears_the_counters_of_the_person_and_the_address(self) -> None:
        flow = Flow()
        challenge = flow.identify.execute(OPERATOR_EMAIL, ADDRESS).challenge_id
        with pytest.raises(BackofficeRefusedError):
            flow.face.execute(challenge, [OTHER_PNG], ADDRESS)
        assert flow.lockouts.rows
        flow.tick()

        flow.password.execute(_to_face_ok(flow), OPERATOR_SECRET, ADDRESS)

        assert flow.lockouts.rows == {}

    def test_a_disabled_operator_is_refused_even_with_the_right_password(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)
        flow.accounts.accounts[flow.operator.id] = type(flow.operator)(
            flow.operator.id,
            flow.operator.email,
            flow.operator.password_hash,
            "operator",
            True,
            True,
        )

        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, OPERATOR_SECRET, ADDRESS)

        assert flow.signer.signed == []

    def test_no_secret_reaches_the_events(self) -> None:
        flow = Flow()
        challenge = _to_face_ok(flow)
        with pytest.raises(BackofficeRefusedError):
            flow.password.execute(challenge, WRONG_SECRET, ADDRESS)
        flow.password.execute(_to_face_ok(flow), OPERATOR_SECRET, ADDRESS)

        text = repr(flow.events.events)

        assert WRONG_SECRET not in text and OPERATOR_SECRET not in text
        assert OPERATOR_EMAIL not in text and "challenge-" not in text


def _fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:8]
