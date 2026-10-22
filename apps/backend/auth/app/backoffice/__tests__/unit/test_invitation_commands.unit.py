import pytest

from app.backoffice import create_operator_invite, revoke_operator_invite
from app.backoffice.__tests__.invitation_flow import INVITED, InvitationFlow
from app.login.__tests__.fakes import make_account


class TestCreateCommand:
    def test_it_prints_one_link_and_the_expiry_and_exits_0(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = InvitationFlow()

        code = create_operator_invite.run(flow.create, INVITED)

        out = capsys.readouterr()
        lines = out.out.strip().splitlines()
        assert code == 0 and out.err == ""
        assert lines[0].startswith("Lien d'invitation (usage unique, valable jusqu'à ")
        assert lines[1].startswith("https://mercure.exemple.test/invitation#token=")
        assert len(lines) == 2

    def test_an_invalid_address_exits_1_with_a_fixed_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = create_operator_invite.run(InvitationFlow().create, "pas-une-adresse")

        out = capsys.readouterr()
        assert (code, out.out, out.err) == (1, "", "Adresse email invalide.\n")

    def test_an_existing_account_exits_1_and_creates_no_link(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = InvitationFlow()
        existing = make_account(INVITED, role="operator")
        flow.accounts.accounts[existing.id] = existing

        code = create_operator_invite.run(flow.create, INVITED)

        out = capsys.readouterr()
        assert code == 1 and out.out == ""
        assert out.err == "Un compte existe déjà avec cette adresse.\n"
        assert flow.store.invitations == {}


class TestRevokeCommand:
    def test_it_reports_the_number_of_revoked_invitations(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = InvitationFlow()
        flow.invite()

        code = revoke_operator_invite.run(flow.revoke, INVITED)

        assert code == 0
        assert capsys.readouterr().out == "1 invitation(s) révoquée(s).\n"

    def test_it_says_so_when_nothing_is_usable(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = revoke_operator_invite.run(InvitationFlow().revoke, INVITED)

        assert code == 0
        assert capsys.readouterr().out == "Aucune invitation utilisable pour cette adresse.\n"

    def test_an_invalid_address_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = revoke_operator_invite.run(InvitationFlow().revoke, "???")

        assert code == 1
        assert capsys.readouterr().err == "Adresse email invalide.\n"


class TestEntryPoints:
    @pytest.mark.parametrize("module", [create_operator_invite, revoke_operator_invite])
    def test_main_exits_1_without_leaking_when_the_setup_is_unusable(
        self,
        module: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def broken(*args: object, **kwargs: object) -> None:
            raise RuntimeError("clé de gabarits absente")

        monkeypatch.setattr(module, "build", broken)
        monkeypatch.setattr(module, "create_engine", lambda *a, **k: object())

        code = module.main(["--email", INVITED])  # type: ignore[attr-defined]

        assert code == 1
        assert capsys.readouterr().err == "clé de gabarits absente\n"

    def test_main_runs_the_command_with_the_built_use_case(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow = InvitationFlow()
        monkeypatch.setattr(create_operator_invite, "build", lambda *a, **k: flow.create)
        monkeypatch.setattr(create_operator_invite, "create_engine", lambda *a, **k: object())

        code = create_operator_invite.main(["--email", INVITED])

        assert code == 0
        assert "#token=" in capsys.readouterr().out
