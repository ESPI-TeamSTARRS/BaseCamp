"""Evenements du service d'observabilite (noms stables, catalogue : docs/services/auth.md)."""

REQUEST_COMPLETED = "service.request_completed"  # une ligne par requete traitee (hors sondes)
METRICS_REFUSED = "service.metrics_refused"  # /metrics demande a travers un proxy (404)
