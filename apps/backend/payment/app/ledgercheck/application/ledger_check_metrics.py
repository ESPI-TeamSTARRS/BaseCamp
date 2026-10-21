"""Nom de la métrique du contrôle du grand livre (catalogue : docs/services/payment.md).

Jauge : nombre d'écarts constatés par le dernier contrôle, 0 quand le grand livre est cohérent. Le
nom est publié ici une fois pour toutes; la lecture se fait par `ReadLedgerDiscrepancyCount`.
"""

LEDGER_DISCREPANCIES = "payment_ledger_discrepancies"
