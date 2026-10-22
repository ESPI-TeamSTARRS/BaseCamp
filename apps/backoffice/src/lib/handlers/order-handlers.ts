import { NextResponse } from 'next/server';
import { buildLogEvent, emit, resolveCorrelationId, type LogEvent } from '../log-event';
import { pseudonymize } from '../pseudonym';
import { isSecure } from '../request-origin';
import { ACCESS_COOKIE } from '../session-cookies';
import { clearSession } from '../session-response';
import type { SessionService } from '../session-service';
import type { ShopClient, ShopFailure } from '../shop-client';
import { readCookie } from './catalog-handlers';

// Routes serveur des commandes (/bff/orders...) : lecture seule, le navigateur n'appelle jamais shop.
// Le jeton reste dans le cookie HttpOnly ; les echecs de shop sont traduits en messages fixes.
// Chaque consultation de detail produit `backoffice.order_view` (audit) avec l'operateur pseudonymise ;
// ni e-mail, ni adresse, ni jeton, ni texte recherche ne sont jamais journalises.

export interface OrderDeps {
  shop: Pick<ShopClient, 'call'>;
  sessions: Pick<SessionService, 'evaluate'>;
  pseudonymKey: string;
  log?: (event: LogEvent) => void;
}

export type OrderAction = 'list' | 'get';

const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const STATUSES = new Set(['pending_payment', 'paid', 'expired', 'refunded']);
const NO_STORE = { 'Cache-Control': 'no-store' };

type Failure = ShopFailure | 'bad_request';

const STATUS: Partial<Record<Failure, number>> = {
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  bad_request: 400,
  invalid: 422,
  unavailable: 503,
};

const MESSAGES: Partial<Record<Failure, string>> = {
  unauthorized: 'Session expirée. Reconnectez-vous.',
  forbidden: 'Accès refusé.',
  not_found: 'Commande introuvable.',
  bad_request: 'Requête invalide.',
  invalid: 'Les données envoyées sont refusées.',
  unavailable: 'Les commandes sont momentanément indisponibles. Réessayez dans un instant.',
};

const DEFAULT_STATUS = 502;
const DEFAULT_MESSAGE = 'Une erreur est survenue. Réessayez.';

// Raisons de refus du jeton qui relevent du droit d'acces (et non d'une session absente ou perimee).
const FORBIDDEN_REASONS = new Set(['not_operator', 'second_factor_missing']);

function listQuery(request: Request): string | null {
  const incoming = new URL(request.url).searchParams;
  const outgoing = new URLSearchParams();
  const limit = incoming.get('limit');
  const offset = incoming.get('offset');
  const status = incoming.get('status');
  const search = incoming.get('q');
  if (limit !== null) {
    if (!/^\d{1,3}$/.test(limit) || Number(limit) < 1 || Number(limit) > 100) return null;
    outgoing.set('limit', limit);
  }
  if (offset !== null) {
    if (!/^\d{1,7}$/.test(offset)) return null;
    outgoing.set('offset', offset);
  }
  if (status !== null && status !== '') {
    if (!STATUSES.has(status)) return null;
    outgoing.set('status', status);
  }
  if (search !== null && search.trim() !== '') {
    if (search.length > 100) return null;
    outgoing.set('q', search.trim());
  }
  const text = outgoing.toString();
  return text ? `?${text}` : '';
}

/** Relaie la consultation des commandes : jeton du cookie verifie (operateur + visage), echecs en messages fixes. */
export async function handleOrders(
  request: Request,
  action: OrderAction,
  orderId: string | undefined,
  deps: OrderDeps
): Promise<NextResponse> {
  const log = deps.log ?? ((event: LogEvent) => emit(event));
  const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
    crypto.randomUUID()
  );
  const event = action === 'get' ? 'backoffice.order_view' : 'backoffice.orders_list';
  const started = Date.now();
  let actorId: string | undefined;

  const fail = (failure: Failure) => {
    log(
      buildLogEvent({
        event,
        correlationId,
        outcome: failure === 'unavailable' || failure === 'error' ? 'error' : 'denied',
        reason: failure,
        durationMs: Date.now() - started,
        resource: action === 'get' ? { type: 'order', id: orderId } : undefined,
        actor: actorId ? { type: 'user', id: actorId } : undefined,
      })
    );
    const response = NextResponse.json(
      { detail: MESSAGES[failure] ?? DEFAULT_MESSAGE, code: failure },
      { status: STATUS[failure] ?? DEFAULT_STATUS, headers: NO_STORE }
    );
    return failure === 'unauthorized' ? clearSession(response, isSecure(request)) : response;
  };

  const token = readCookie(request, ACCESS_COOKIE);
  if (!token) return fail('unauthorized');
  const session = await deps.sessions.evaluate(token);
  if (session.kind === 'error') return fail('unavailable');
  if (session.kind === 'none')
    return fail(FORBIDDEN_REASONS.has(session.reason) ? 'forbidden' : 'unauthorized');
  actorId = pseudonymize(session.claims.sub, deps.pseudonymKey);

  let path: string;
  if (action === 'list') {
    const query = listQuery(request);
    if (query === null) return fail('bad_request');
    path = `/admin/orders${query}`;
  } else {
    if (orderId === undefined || !ID_RE.test(orderId)) return fail('bad_request');
    path = `/admin/orders/${orderId}`;
  }

  const reply = await deps.shop.call({ method: 'GET', path, token, correlationId });
  if (!reply.ok) return fail(reply.failure);
  log(
    buildLogEvent({
      event,
      correlationId,
      outcome: 'success',
      durationMs: Date.now() - started,
      resource: action === 'get' ? { type: 'order', id: orderId } : undefined,
      actor: { type: 'user', id: actorId },
      attributes: { status: reply.status },
    })
  );
  return NextResponse.json(reply.data, { status: reply.status, headers: NO_STORE });
}
