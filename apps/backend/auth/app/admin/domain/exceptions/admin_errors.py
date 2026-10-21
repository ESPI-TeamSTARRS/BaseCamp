class AdminError(Exception):
    """Erreur metier de l'administration : code stable et message fixe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AccountNotFoundError(AdminError):
    def __init__(self) -> None:
        super().__init__("account_not_found", "Compte introuvable.")


class CannotDisableSelfError(AdminError):
    def __init__(self) -> None:
        super().__init__("cannot_disable_self", "Un opérateur ne peut pas se désactiver lui-même.")


class CannotDisableLastOperatorError(AdminError):
    def __init__(self) -> None:
        super().__init__(
            "cannot_disable_last_operator", "Le dernier opérateur actif ne peut pas être désactivé."
        )


class OperatorAlreadyExistsError(AdminError):
    def __init__(self) -> None:
        super().__init__("operator_exists", "Un compte existe déjà avec cette adresse.")
