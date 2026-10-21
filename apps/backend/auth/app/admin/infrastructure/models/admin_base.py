from sqlalchemy.orm import DeclarativeBase


class AdminBase(DeclarativeBase):
    """Base declarative de la tranche admin : elle ne declare que les colonnes qu'elle utilise.

    La table `users` appartient a l'inscription (et `disabled_at` a la connexion) : l'administration
    en lit et en ecrit un sous-ensemble, avec une base distincte (aucun import entre tranches).
    """
