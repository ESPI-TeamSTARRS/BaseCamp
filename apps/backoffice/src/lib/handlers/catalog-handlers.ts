import { NextResponse } from 'next/server';
import { buildLogEvent, emit, resolveCorrelationId, type LogEvent } from '../log-event';
import { isSameOrigin, isSecure } from '../request-origin';
import { ACCESS_COOKIE } from '../session-cookies';
import { clearSession } from '../session-response';
import type { ShopClient, ShopFailure } from '../shop-client';

// Routes serveur du catalogue (/bff/products...) : le navigateur n'appelle jamais shop directement.
// Le jeton reste dans le cookie HttpOnly ; les echecs de shop sont traduits en messages fixes.

export interface CatalogDeps {
  shop: Pick<ShopClient, 'call'>;
  log?: (event: LogEvent) => void;
}

export type CatalogAction = 'list' | 'create' | 'get' | 'update' | 'archive' | 'image';

const JSON_LIMIT = 64 * 1024;
export const IMAGE_LIMIT = 2 * 1024 * 1024;
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const NO_STORE = { 'Cache-Control': 'no-store' };

const STATUS: Record<ShopFailure, number> = {
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  stale_version: 409,
  archived: 409,
  duplicate: 409,
  too_many_images: 409,
  conflict: 409,
  invalid: 422,
  unavailable: 503,
  error: 502,
};

const MESSAGES: Record<ShopFailure, string> = {
  unauthorized: 'Session expirée. Reconnectez-vous.',
  forbidden: 'Accès refusé.',
  not_found: 'Produit introuvable.',
  stale_version:
    'Ce produit a été modifié ailleurs depuis son ouverture. Rechargez-le pour voir la dernière version.',
  archived: 'Ce produit est archivé et ne peut plus être modifié.',
  duplicate: 'Un produit portant cet identifiant existe déjà.',
  too_many_images: 'Le nombre maximal d’images est atteint.',
  conflict: 'Conflit : l’opération n’a pas pu être appliquée.',
  invalid: 'Les données envoyées sont refusées.',
  unavailable: 'Le catalogue est momentanément indisponible. Réessayez dans un instant.',
  error: 'Une erreur est survenue. Réessayez.',
};

const IMAGE_REFUSED = 'Image refusée : JPEG, PNG ou WebP, 2 Mo au plus.';

type Failure = ShopFailure | 'cross_origin' | 'bad_request' | 'too_large';

export function readCookie(request: Request, name: string): string | undefined {
  for (const part of (request.headers.get('cookie') ?? '').split(';')) {
    const [key, ...value] = part.trim().split('=');
    if (key === name) return value.join('=') || undefined;
  }
  return undefined;
}

function sendFailure(request: Request, failure: Failure, action: CatalogAction): NextResponse {
  let status: number;
  let detail: string;
  if (failure === 'cross_origin') [status, detail] = [403, 'Requête refusée.'];
  else if (failure === 'bad_request') [status, detail] = [400, 'Requête invalide.'];
  else if (failure === 'too_large')
    [status, detail] = [413, action === 'image' ? IMAGE_REFUSED : 'Requête trop volumineuse.'];
  else {
    status = STATUS[failure];
    detail = failure === 'invalid' && action === 'image' ? IMAGE_REFUSED : MESSAGES[failure];
  }
  const response = NextResponse.json({ detail, code: failure }, { status, headers: NO_STORE });
  return failure === 'unauthorized' ? clearSession(response, isSecure(request)) : response;
}

async function readLimited(request: Request, limit: number): Promise<Uint8Array | null> {
  const declared = Number(request.headers.get('content-length') ?? '0');
  if (Number.isFinite(declared) && declared > limit) return null;
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

async function readObject(request: Request): Promise<Record<string, unknown> | 'too_large' | null> {
  const bytes = await readLimited(request, JSON_LIMIT);
  if (bytes === null) return 'too_large';
  try {
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return typeof value === 'object' && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function listQuery(request: Request): string | null {
  const incoming = new URL(request.url).searchParams;
  const outgoing = new URLSearchParams();
  const limit = incoming.get('limit');
  const offset = incoming.get('offset');
  const archived = incoming.get('include_archived');
  const search = incoming.get('q');
  if (limit !== null) {
    if (!/^\d{1,3}$/.test(limit) || Number(limit) < 1 || Number(limit) > 100) return null;
    outgoing.set('limit', limit);
  }
  if (offset !== null) {
    if (!/^\d{1,7}$/.test(offset)) return null;
    outgoing.set('offset', offset);
  }
  if (archived !== null) {
    if (archived !== 'true' && archived !== 'false') return null;
    outgoing.set('include_archived', archived);
  }
  if (search !== null && search.trim() !== '') {
    if (search.length > 100) return null;
    outgoing.set('q', search.trim());
  }
  const text = outgoing.toString();
  return text ? `?${text}` : '';
}

/** Relaie une action du catalogue : controle d'origine, jeton du cookie, traduction des echecs. */
export async function handleCatalog(
  request: Request,
  action: CatalogAction,
  productId: string | undefined,
  deps: CatalogDeps
): Promise<NextResponse> {
  const log = deps.log ?? ((event: LogEvent) => emit(event));
  const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
    crypto.randomUUID()
  );
  const event = `backoffice.catalog_${action}`;
  const started = Date.now();
  const fail = (failure: Failure) => {
    log(
      buildLogEvent({
        event,
        correlationId,
        outcome: failure === 'unavailable' || failure === 'error' ? 'error' : 'denied',
        reason: failure,
        durationMs: Date.now() - started,
      })
    );
    return sendFailure(request, failure, action);
  };

  const writes = action !== 'list' && action !== 'get';
  if (writes && !isSameOrigin(request)) return fail('cross_origin');
  const token = readCookie(request, ACCESS_COOKIE);
  if (!token) return fail('unauthorized');
  if (productId !== undefined && !ID_RE.test(productId)) return fail('bad_request');

  let call;
  if (action === 'list') {
    const query = listQuery(request);
    if (query === null) return fail('bad_request');
    call = { method: 'GET', path: `/admin/products${query}` } as const;
  } else if (action === 'get') {
    call = { method: 'GET', path: `/admin/products/${productId}` } as const;
  } else if (action === 'archive') {
    call = { method: 'POST', path: `/admin/products/${productId}/archive` } as const;
  } else if (action === 'image') {
    const bytes = await readLimited(request, IMAGE_LIMIT);
    if (bytes === null) return fail('too_large');
    call = { method: 'POST', path: `/admin/products/${productId}/image`, bytes } as const;
  } else {
    const body = await readObject(request);
    if (body === 'too_large') return fail('too_large');
    if (body === null) return fail('bad_request');
    call =
      action === 'create'
        ? ({ method: 'POST', path: '/admin/products', json: body } as const)
        : ({ method: 'PATCH', path: `/admin/products/${productId}`, json: body } as const);
  }

  const reply = await deps.shop.call({ ...call, token, correlationId });
  if (!reply.ok) return fail(reply.failure);
  log(
    buildLogEvent({
      event,
      correlationId,
      outcome: 'success',
      durationMs: Date.now() - started,
      attributes: { status: reply.status },
    })
  );
  return NextResponse.json(reply.data, { status: reply.status, headers: NO_STORE });
}
