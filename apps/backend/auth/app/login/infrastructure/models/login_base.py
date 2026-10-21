from sqlalchemy.orm import DeclarativeBase


class LoginBase(DeclarativeBase):
    """Base declarative de la tranche login : elle ne declare que les colonnes qu'elle utilise.

    La table `users` appartient a l'inscription ; la connexion en lit un sous-ensemble et y ajoute
    `disabled_at` (migration 0004). Deux bases distinctes evitent tout import entre tranches.
    """
