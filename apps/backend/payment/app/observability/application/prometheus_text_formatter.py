from collections.abc import Iterable, Mapping

from app.observability.domain.entities.request_metrics_snapshot import RequestMetricsSnapshot
from app.observability.domain.entities.service_state import ServiceState

_ESCAPES = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n"})


def _labels(**labels: str | int) -> str:
    inner = ",".join(f'{name}="{str(value).translate(_ESCAPES)}"' for name, value in labels.items())
    return f"{{{inner}}}"


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


class PrometheusTextFormatter:
    """Écrit le format texte Prometheus 0.0.4 : HELP, TYPE puis les échantillons de chaque famille."""

    def format(self, snapshot: RequestMetricsSnapshot, state: ServiceState | None) -> str:
        lines: list[str] = []
        self._requests(lines, snapshot)
        self._latencies(lines, snapshot)
        if state is not None:
            self._state(lines, state)
        self._family(
            lines,
            "payment_state_up",
            "gauge",
            "1 si l'état métier a pu être lu en base pendant cette collecte, 0 sinon.",
            [f"payment_state_up {1 if state is not None else 0}"],
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _family(
        lines: list[str], name: str, kind: str, help_text: str, samples: Iterable[str]
    ) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        lines.extend(samples)

    def _requests(self, lines: list[str], snapshot: RequestMetricsSnapshot) -> None:
        ordered = sorted(
            snapshot.requests.items(),
            key=lambda item: (item[0].route, item[0].method, item[0].status),
        )
        samples = [
            "payment_http_requests_total"
            + _labels(route=key.route, method=key.method, status=key.status)
            + f" {count}"
            for key, count in ordered
        ]
        self._family(
            lines,
            "payment_http_requests_total",
            "counter",
            "Requêtes traitées par ce processus, par route (gabarit), méthode et statut.",
            samples,
        )

    def _latencies(self, lines: list[str], snapshot: RequestMetricsSnapshot) -> None:
        name = "payment_http_request_duration_seconds"
        samples: list[str] = []
        for (route, method), distribution in sorted(snapshot.latencies.items()):
            base = {"route": route, "method": method}
            for bound, count in zip(
                distribution.bounds, distribution.cumulative_counts, strict=True
            ):
                samples.append(f"{name}_bucket{_labels(**base, le=repr(float(bound)))} {count}")
            samples.append(f"{name}_bucket{_labels(**base, le='+Inf')} {distribution.count}")
            samples.append(f"{name}_sum{_labels(**base)} {_number(distribution.total_seconds)}")
            samples.append(f"{name}_count{_labels(**base)} {distribution.count}")
        self._family(
            lines, name, "histogram", "Durée de traitement des requêtes, en secondes.", samples
        )

    def _state(self, lines: list[str], state: ServiceState) -> None:
        self._gauge_by(
            lines,
            "payment_intents",
            "status",
            "Intentions de paiement par statut.",
            state.intents_by_status,
        )
        self._gauge_by(
            lines,
            "payment_webhook_events",
            "status",
            "Événements webhook de l'outbox par statut (pending, delivered, dead).",
            state.webhook_events_by_status,
        )
        self._gauge(
            lines,
            "payment_webhook_oldest_pending_age_seconds",
            "Ancienneté en secondes du plus ancien événement webhook pending (0 si aucun).",
            state.webhook_oldest_pending_age_seconds,
        )
        self._gauge(
            lines,
            "payment_captured_amount_cents",
            "Somme des montants des intentions réussies, en centimes.",
            state.captured_amount_cents,
        )
        self._gauge(
            lines,
            "payment_refunded_amount_cents",
            "Somme des montants remboursés sur les intentions réussies, en centimes.",
            state.refunded_amount_cents,
        )
        self._gauge(
            lines,
            "payment_refunded_intents",
            "Nombre d'intentions réussies ayant au moins un remboursement.",
            state.refunded_intents,
        )
        self._gauge_by(
            lines,
            "payment_ledger_discrepancies",
            "kind",
            "Écarts du grand livre sur la fenêtre de contrôle, par nature (0 attendu).",
            state.ledger_discrepancies,
        )

    def _gauge(self, lines: list[str], name: str, help_text: str, value: float) -> None:
        self._family(lines, name, "gauge", help_text, [f"{name} {_number(value)}"])

    def _gauge_by(
        self, lines: list[str], name: str, label: str, help_text: str, values: Mapping[str, int]
    ) -> None:
        samples = [f"{name}{_labels(**{label: key})} {value}" for key, value in values.items()]
        self._family(lines, name, "gauge", help_text, samples)
