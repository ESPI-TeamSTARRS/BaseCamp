from collections.abc import Iterable, Mapping

from app.observability.domain.entities.request_metrics_snapshot import RequestMetricsSnapshot
from app.observability.domain.entities.service_state import ServiceState
from app.observability.domain.value_objects.event_key import EventKey

_ESCAPES = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n"})

LOGIN_FAILED = "auth.login_failed"
LOGIN_SUCCEEDED = "auth.login_succeeded"
LOCKOUT_TRIGGERED = "auth.lockout_triggered"
REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
SERVICE_TOKEN_DENIED = "auth.service_token_denied"  # noqa: S105
SERVICE_RATE_LIMITED = "auth.service_rate_limited"
BACKOFFICE_LOCKOUT = "auth.backoffice_lockout"
# Evenement de resultat de chaque temps de la connexion du back-office -> etape (libelle ferme).
BACKOFFICE_STEPS = {
    "auth.backoffice_identify": "identify",
    "auth.backoffice_face_result": "face",
    "auth.backoffice_password_result": "password",
}


def _labels(**labels: str | int) -> str:
    inner = ",".join(f'{name}="{str(value).translate(_ESCAPES)}"' for name, value in labels.items())
    return f"{{{inner}}}"


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


class PrometheusTextFormatter:
    """Ecrit le format texte Prometheus 0.0.4 : HELP, TYPE puis les echantillons de chaque famille.

    Les libelles sont une liste fermee : `route` (gabarit), `method`, `status`, `le`, `event`,
    `outcome`, `reason`, `cause`, `step`, `result` (success, denied, error), `client` (client de
    service connu ou `unknown`).
    Jamais d'adresse, de mot de passe, de jeton ni de secret.
    """

    def format(self, snapshot: RequestMetricsSnapshot, state: ServiceState | None) -> str:
        lines: list[str] = []
        self._requests(lines, snapshot)
        self._latencies(lines, snapshot)
        self._events(lines, snapshot)
        self._signals(lines, snapshot)
        if state is not None:
            self._state(lines, state)
        self._family(
            lines,
            "auth_state_up",
            "gauge",
            "1 si l'état métier a pu être lu en base pendant cette collecte, 0 sinon.",
            [f"auth_state_up {1 if state is not None else 0}"],
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
            "auth_http_requests_total"
            + _labels(route=key.route, method=key.method, status=key.status)
            + f" {count}"
            for key, count in ordered
        ]
        self._family(
            lines,
            "auth_http_requests_total",
            "counter",
            "Requêtes traitées par ce processus, par route (gabarit), méthode et statut.",
            samples,
        )

    def _latencies(self, lines: list[str], snapshot: RequestMetricsSnapshot) -> None:
        name = "auth_http_request_duration_seconds"
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

    def _events(self, lines: list[str], snapshot: RequestMetricsSnapshot) -> None:
        totals: dict[tuple[str, str, str], int] = {}
        for key, count in snapshot.events.items():
            series = (key.event, key.outcome, key.reason)
            totals[series] = totals.get(series, 0) + count
        samples = [
            "auth_events_total" + _labels(event=event, outcome=outcome, reason=reason) + f" {count}"
            for (event, outcome, reason), count in sorted(totals.items())
        ]
        self._family(
            lines,
            "auth_events_total",
            "counter",
            "Événements métier émis par ce processus (les mêmes que le journal), par nom, résultat et motif.",
            samples,
        )

    def _signals(self, lines: list[str], snapshot: RequestMetricsSnapshot) -> None:
        events = snapshot.events
        self._counter_by(
            lines,
            "auth_login_failures_total",
            "cause",
            "Échecs de connexion, par cause interne (unknown_account, wrong_password, account_disabled, account_locked).",
            self._sum_by_detail(events, LOGIN_FAILED),
        )
        self._counter_by(
            lines,
            "auth_lockouts_triggered_total",
            "step",
            "Verrous posés (nombre d'événements), par étape verrouillée.",
            self._sum_by_detail(events, LOCKOUT_TRIGGERED),
        )
        self._counter_by(
            lines,
            "auth_refresh_reuse_detected_total",
            None,
            "Réutilisations d'un jeton de rafraîchissement déjà consommé (famille révoquée).",
            self._sum_by_detail(events, REFRESH_REUSE_DETECTED),
        )
        self._backoffice_attempts(lines, events)
        self._counter_by(
            lines,
            "auth_backoffice_lockouts_total",
            "step",
            "Blocages de la connexion du back-office (nombre d'événements), par étape verrouillée.",
            self._sum_by_detail(events, BACKOFFICE_LOCKOUT),
        )
        self._counter_by(
            lines,
            "auth_service_token_denied_total",
            "client",
            "Jetons de service refusés, par client connu (`unknown` pour tout autre identifiant).",
            self._sum_by_detail(events, SERVICE_TOKEN_DENIED),
        )
        self._counter_by(
            lines,
            "auth_service_token_rate_limited_total",
            "client",
            "Demandes de jeton de service limitées en débit, par client connu (`unknown` sinon).",
            self._sum_by_detail(events, SERVICE_RATE_LIMITED),
        )

    def _backoffice_attempts(self, lines: list[str], events: Mapping[EventKey, int]) -> None:
        totals: dict[tuple[str, str], int] = {}
        for key, count in events.items():
            step = BACKOFFICE_STEPS.get(key.event)
            if step is not None:
                totals[(step, key.outcome)] = totals.get((step, key.outcome), 0) + count
        samples = [
            "auth_backoffice_attempts_total" + _labels(step=step, result=result) + f" {count}"
            for (step, result), count in sorted(totals.items())
        ]
        self._family(
            lines,
            "auth_backoffice_attempts_total",
            "counter",
            "Tentatives de connexion du back-office, par étape (identify, face, password) et résultat (success, denied, error).",
            samples,
        )

    @staticmethod
    def _sum_by_detail(events: Mapping[EventKey, int], name: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for key, count in events.items():
            if key.event == name:
                totals[key.detail] = totals.get(key.detail, 0) + count
        return totals

    def _counter_by(
        self,
        lines: list[str],
        name: str,
        label: str | None,
        help_text: str,
        values: dict[str, int],
    ) -> None:
        if label is None:
            samples = [f"{name} {sum(values.values())}"]
        else:
            samples = [
                f"{name}{_labels(**{label: detail})} {count}"
                for detail, count in sorted(values.items())
            ]
        self._family(lines, name, "counter", help_text, samples)

    def _state(self, lines: list[str], state: ServiceState) -> None:
        samples = [
            f"auth_active_lockouts{_labels(step=step)} {count}"
            for step, count in sorted(state.active_lockouts_by_step.items())
        ]
        self._family(
            lines,
            "auth_active_lockouts",
            "gauge",
            "Sujets actuellement verrouillés, par étape (lu en base à chaque collecte).",
            samples,
        )
