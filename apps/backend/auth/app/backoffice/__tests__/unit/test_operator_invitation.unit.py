from datetime import timedelta

import pytest

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.__tests__.invitation_flow import (
    ADDRESS,
    BASE_URL,
    GOOD_PASSWORD,
    INVITED,
    InvitationFlow,
    digest_of,
)
from app.backoffice.application.create_operator_invitation import InvitationAddressTakenError
from app.backoffice.application.invitation_errors import (
    InvitationPasswordError,
    InvitationPhotoError,
    InvitationRefusedError,
)
from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.core.events.outcome import Outcome
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError

PHOTOS = [PNG, JPEG, OTHER_PNG]


def _complete(flow: InvitationFlow, token: str, **overrides: object) -> object:
    options: dict[str, object] = {
        "token": token,
        "password": GOOD_PASSWORD,
        "photos": PHOTOS,
        "client_ip": ADDRESS,
    }
    options.update(overrides)
    return flow.complete.execute(**options)  # type: ignore[arg-type]


class TestCreation:
    def test_it_gives_a_link_with_a_random_token_on_the_admin_origin(self) -> None:
        flow = InvitationFlow()

        created = flow.create.execute(INVITED)

        assert created.link.startswith(f"{BASE_URL}/invitation#token=")
        assert len(created.link.split("#token=")[1]) > 0
        assert repr(created).count("token") == 0  # le lien n'est pas dans la representation

    def test_only_the_hash_of_the_token_is_stored(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        (digest,) = flow.store.invitations
        assert digest == digest_of(token)
        assert token not in repr(flow.store.invitations)

    def test_it_lives_five_minutes_at_most_even_when_asked_longer(self) -> None:
        flow = InvitationFlow()
        flow.create._ttl = 3600

        created = flow.create.execute(INVITED)

        assert created.expires_at - flow.clock.now() == timedelta(minutes=5)

    def test_it_is_bound_to_the_invited_address_normalised(self) -> None:
        flow = InvitationFlow()

        flow.create.execute("  Nouvel.Operateur@Example.com ")

        (invitation,) = flow.store.invitations.values()
        assert invitation.email == INVITED

    def test_an_invalid_address_is_refused(self) -> None:
        with pytest.raises(InvalidEmailError):
            InvitationFlow().create.execute("pas-une-adresse")

    def test_an_address_that_already_has_an_account_cannot_be_invited(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        _complete(flow, token)

        with pytest.raises(InvitationAddressTakenError):
            flow.create.execute(INVITED)

    def test_inviting_again_revokes_the_previous_link(self) -> None:
        flow = InvitationFlow()
        first = flow.invite()
        second = flow.invite()

        with pytest.raises(InvitationRefusedError):
            _complete(flow, first)
        assert _complete(flow, second)

    def test_the_event_names_the_address_hash_only_and_never_the_token(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        (event,) = flow.events.events
        assert event.event == "auth.operator_invite_created"
        assert event.outcome is Outcome.SUCCESS
        text = repr(event)
        assert INVITED not in text and token not in text and "token=" not in text

    def test_old_invitations_are_purged(self) -> None:
        flow = InvitationFlow()
        flow.invite()
        flow.tick(2 * 24 * 3600)

        flow.invite("autre@example.com")

        assert len(flow.store.invitations) == 1


class TestCompletion:
    def test_a_valid_link_creates_the_operator_and_the_template_in_one_transaction(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        commits = flow.store.commits

        account_id = _complete(flow, token)

        account = flow.accounts.accounts[account_id]  # type: ignore[index]
        assert (account.email, account.role, account.disabled) == (INVITED, "operator", False)
        assert account.password_hash != GOOD_PASSWORD and account.email_verified
        assert len(flow.store.templates[account_id]) == 2069  # type: ignore[index]
        assert flow.store.commits == commits + 1  # une seule transaction

    def test_the_token_is_consumed(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        _complete(flow, token)

        with pytest.raises(InvitationRefusedError):
            _complete(flow, token)

    @pytest.mark.parametrize("token", ["inconnu", "", "x" * 40])
    def test_an_unknown_token_is_refused_with_the_generic_error(self, token: str) -> None:
        flow = InvitationFlow()

        with pytest.raises(InvitationRefusedError) as raised:
            _complete(flow, token)

        assert raised.value.message == "Invitation invalide ou expirée."

    def test_an_expired_token_is_refused(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        flow.tick(5 * 60 + 1)

        with pytest.raises(InvitationRefusedError):
            _complete(flow, token)

        assert flow.accounts.accounts == {}

    def test_a_revoked_token_is_refused(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        assert flow.revoke.execute(INVITED) == 1

        with pytest.raises(InvitationRefusedError):
            _complete(flow, token)

    def test_without_any_invitation_no_operator_can_be_created(self) -> None:
        flow = InvitationFlow()

        for guess in ("a", "b", "c"):
            with pytest.raises(InvitationRefusedError):
                _complete(flow, guess)

        assert flow.accounts.accounts == {} and flow.store.templates == {}

    def test_a_weak_password_is_a_422_and_the_token_stays_valid(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        with pytest.raises(InvitationPasswordError) as raised:
            _complete(flow, token, password="court")

        assert raised.value.code == "password_too_short"
        assert flow.accounts.accounts == {}
        assert _complete(flow, token)  # le jeton n'est pas consomme

    @pytest.mark.parametrize("count", [0, 2, 11])
    def test_the_photo_count_is_bounded_to_three_to_ten(self, count: int) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        with pytest.raises(InvitationPhotoError) as raised:
            _complete(flow, token, photos=[PNG] * count)

        assert raised.value.code == "photo_count"
        assert flow.accounts.accounts == {}
        assert _complete(flow, token)

    @pytest.mark.parametrize(
        "photo", [b"", b"GIF89a-x", PNG + b"x" * 1_048_577], ids=["vide", "gif", "plus-d-un-mo"]
    )
    def test_a_photo_that_is_not_a_small_jpeg_or_png_is_refused_without_side_effect(
        self, photo: bytes
    ) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        with pytest.raises(InvitationPhotoError) as raised:
            _complete(flow, token, photos=[PNG, PNG, photo])

        assert raised.value.code == "invalid_photo"
        assert flow.accounts.accounts == {}
        assert _complete(flow, token)

    def test_a_photo_without_a_face_creates_no_account_and_keeps_the_token(self) -> None:
        class NoFace(FakeReconnaissanceFaciale):
            def enroler(self, photos: list[bytes]) -> bytes:
                raise AucunVisage

        flow = InvitationFlow(NoFace())
        token = flow.invite()

        with pytest.raises(InvitationPhotoError) as raised:
            _complete(flow, token)

        assert raised.value.code == "no_face"
        assert flow.accounts.accounts == {} and flow.store.templates == {}
        assert flow.store.invitations[digest_of(token)].consumed_at is None

    def test_an_unreadable_photo_for_the_recognizer_changes_nothing(self) -> None:
        class Unreadable(FakeReconnaissanceFaciale):
            def enroler(self, photos: list[bytes]) -> bytes:
                raise ImageInvalide

        flow = InvitationFlow(Unreadable())
        token = flow.invite()

        with pytest.raises(InvitationPhotoError):
            _complete(flow, token)

        assert flow.accounts.accounts == {}
        assert flow.store.invitations[digest_of(token)].consumed_at is None

    def test_an_enrolment_failure_never_counts_as_a_login_attempt(self) -> None:
        class NoFace(FakeReconnaissanceFaciale):
            def enroler(self, photos: list[bytes]) -> bytes:
                raise AucunVisage

        flow = InvitationFlow(NoFace())
        token = flow.invite()
        for _ in range(8):
            with pytest.raises(InvitationPhotoError):
                _complete(flow, token)

        assert flow.lockouts.rows == {}

    def test_a_failure_while_writing_rolls_everything_back(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()

        def failing(*args: object, **kwargs: object) -> None:
            raise RuntimeError("panne base")

        flow.store.accounts.accounts.clear()
        original = flow.complete._unit_of_work

        def broken_factory():  # type: ignore[no-untyped-def]
            work = original()
            work.templates.save = failing  # type: ignore[method-assign]
            return work

        flow.complete._unit_of_work = broken_factory

        with pytest.raises(RuntimeError):
            _complete(flow, token)

        assert flow.accounts.accounts == {} and flow.store.templates == {}
        assert flow.store.invitations[digest_of(token)].consumed_at is None

    def test_an_account_created_in_the_meantime_gives_the_generic_refusal(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        from app.login.__tests__.fakes import make_account

        taken = make_account(INVITED, role="operator")
        flow.accounts.accounts[taken.id] = taken

        with pytest.raises(InvitationRefusedError):
            _complete(flow, token)

        assert len(flow.accounts.accounts) == 1

    def test_the_new_operator_can_pass_the_face_step_with_the_enrolled_photo(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        account_id = _complete(flow, token)

        template = flow.store.templates[account_id]  # type: ignore[index]

        assert flow.recognizer.verifier(PNG, template) is True


class TestLockout:
    def test_five_unknown_tokens_from_one_address_lock_it_for_five_minutes(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        for index in range(5):
            with pytest.raises(InvitationRefusedError):
                _complete(flow, f"faux-{index}")

        with pytest.raises(InvitationRefusedError):
            _complete(flow, token)  # meme le bon jeton est refuse : l'adresse est bloquee

        assert any(e.event == "auth.lockout_triggered" for e in flow.events.events)
        flow.tick(5 * 60)
        flow.tick(1)
        flow.create._ttl = 300
        fresh = flow.invite()
        assert _complete(flow, fresh)

    def test_another_address_is_not_blocked(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        for index in range(5):
            with pytest.raises(InvitationRefusedError):
                _complete(flow, f"faux-{index}")

        assert _complete(flow, token, client_ip="198.51.100.77")

    def test_a_success_clears_the_counter_of_the_address(self) -> None:
        flow = InvitationFlow()
        for index in range(3):
            with pytest.raises(InvitationRefusedError):
                _complete(flow, f"faux-{index}")
        _complete(flow, flow.invite())

        assert flow.lockouts.rows == {}


class TestRevocation:
    def test_it_revokes_the_usable_invitations_of_an_address(self) -> None:
        flow = InvitationFlow()
        flow.invite()

        assert flow.revoke.execute("  NOUVEL.operateur@example.com") == 1
        assert flow.revoke.execute(INVITED) == 0

    def test_it_does_not_touch_the_invitations_of_other_addresses(self) -> None:
        flow = InvitationFlow()
        other = flow.invite("autre@example.com")
        flow.invite()

        flow.revoke.execute(INVITED)

        assert _complete(flow, other)

    def test_an_invalid_address_is_refused(self) -> None:
        with pytest.raises(InvalidEmailError):
            InvitationFlow().revoke.execute("n'importe quoi")

    def test_it_is_journaled_with_the_hash_and_the_count(self) -> None:
        flow = InvitationFlow()
        flow.invite()
        flow.revoke.execute(INVITED)

        revoked = [e for e in flow.events.events if e.event == "auth.operator_invite_revoked"]
        assert [dict(e.attributes)["revoked"] for e in revoked] == [1]
        assert INVITED not in repr(revoked)


class TestLogs:
    def test_no_token_password_photo_template_or_address_reaches_the_events(self) -> None:
        flow = InvitationFlow()
        token = flow.invite()
        with pytest.raises(InvitationPasswordError):
            _complete(flow, token, password="court")
        with pytest.raises(InvitationRefusedError):
            _complete(flow, "faux")
        _complete(flow, token)

        text = repr(flow.events.events)

        for forbidden in (token, GOOD_PASSWORD, "PNG", INVITED, "token="):
            assert forbidden not in text

    def test_the_refusals_carry_the_client_address_and_a_closed_reason(self) -> None:
        flow = InvitationFlow()
        with pytest.raises(InvitationRefusedError):
            _complete(flow, "faux")

        refused = [e for e in flow.events.events if e.event == "auth.operator_invite_refused"]
        assert [(e.reason, e.client_ip) for e in refused] == [("invalid_token", ADDRESS)]
