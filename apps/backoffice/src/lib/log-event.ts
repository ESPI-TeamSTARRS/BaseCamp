// Evenement de journal metier du back-office, au contrat commun (docs/development/logging.md) :
// un document JSON par ligne sur la sortie standard, sans donnee personnelle ni secret.

export const SERVICE_NAME = 'basecamp-backoffice';

const CORRELATION_ID_RE = /^[A-Za-z0-9-]{8,64}$/;

export type Outcome = 'success' | 'denied' | 'error';

export interface LogEvent {
  timestamp: string;
  service: string;
  level: 'info' | 'warning' | 'error';
  event: string;
  correlation_id: string;
  outcome: Outcome;
  reason?: string;
  duration_ms?: number;
}

const LEVELS: Record<Outcome, LogEvent['level']> = { success: 'info', denied: 'warning', error: 'error' };

/** Retient l'identifiant de correlation recu seulement s'il est bien forme, sinon en genere un. */
export function resolveCorrelationId(received: string | null | undefined, generate: () => string): string {
  return received && CORRELATION_ID_RE.test(received) ? received : generate();
}

export function buildLogEvent(input: {
  event: string;
  correlationId: string;
  outcome: Outcome;
  reason?: string;
  durationMs?: number;
  now?: Date;
}): LogEvent {
  if (input.outcome !== 'success' && !input.reason) {
    throw new Error('reason est obligatoire quand outcome vaut denied ou error');
  }
  const event: LogEvent = {
    timestamp: (input.now ?? new Date()).toISOString(),
    service: SERVICE_NAME,
    level: LEVELS[input.outcome],
    event: input.event,
    correlation_id: input.correlationId,
    outcome: input.outcome,
  };
  if (input.reason) event.reason = input.reason;
  if (input.durationMs !== undefined) event.duration_ms = input.durationMs;
  return event;
}

export function emit(event: LogEvent, write: (line: string) => void = console.log): void {
  write(JSON.stringify(event));
}
