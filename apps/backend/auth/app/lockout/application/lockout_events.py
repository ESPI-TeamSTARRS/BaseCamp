"""Catalogue des evenements metier du verrouillage (noms et motifs stables, jamais renommes).

Chaque evenement porte `step` (l'etape verrouillee : `password`, `identifier`, `face`, ...) pour
qu'un parcours en plusieurs temps se lise dans les journaux sans changer le schema.
"""

LOCKOUT_TRIGGERED = "auth.lockout_triggered"

REASON_TOO_MANY_FAILURES = "too_many_failures"

RESOURCE_SUBJECT = "lockout_subject"
