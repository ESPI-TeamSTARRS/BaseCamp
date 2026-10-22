from sqlalchemy.orm import DeclarativeBase


class BackofficeBase(DeclarativeBase):
    """Base declarative de la tranche back-office : elle ne declare que ses propres tables.

    Les cles etrangeres vers `users` (tranche inscription) sont portees par la migration, pas par un
    import entre tranches.
    """
