// Appels du back-office a l'API d'administration du catalogue de `shop` (reseau interne `app`).
// Le jeton de l'operateur vient du cookie de session ; jamais renvoye au navigateur ni journalise.
// Aucune erreur de shop n'est reflechie telle quelle : le gestionnaire ne retient que la nature de l'echec.

export type ShopFailure =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'stale_version'
  | 'archived'
  | 'duplicate'
  | 'too_many_images'
  | 'conflict'
  | 'invalid'
  | 'unavailable'
  | 'error';

export type ShopReply =
  { ok: true; status: number; data: unknown } | { ok: false; failure: ShopFailure; status: number };

export interface ShopCall {
  method: 'GET' | 'POST' | 'PATCH';
  path: string;
  token: string;
  correlationId: string;
  json?: unknown;
  bytes?: Uint8Array;
}

type FetchLike = typeof fetch;

const TIMEOUT_MS = 12_000;

// Messages de conflit de shop (409) -> nature du conflit.
const CONFLICTS: Record<string, ShopFailure> = {
  'Version perimee.': 'stale_version',
  'Produit archive.': 'archived',
  'Produit deja existant.': 'duplicate',
  "Nombre maximal d'images atteint.": 'too_many_images',
};

export class ShopClient {
  constructor(
    private readonly baseUrl: string,
    private readonly fetchImpl: FetchLike = fetch
  ) {}

  async call(call: ShopCall): Promise<ShopReply> {
    const headers = new Headers({
      authorization: `Bearer ${call.token}`,
      'x-correlation-id': call.correlationId,
      accept: 'application/json',
    });
    let body: BodyInit | undefined;
    if (call.json !== undefined) {
      headers.set('content-type', 'application/json');
      body = JSON.stringify(call.json);
    } else if (call.bytes !== undefined) {
      headers.set('content-type', 'application/octet-stream');
      body = call.bytes as BodyInit;
    }
    let reply: Response;
    try {
      reply = await this.fetchImpl(`${this.baseUrl}${call.path}`, {
        method: call.method,
        headers,
        body,
        redirect: 'error',
        cache: 'no-store',
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      return { ok: false, failure: 'unavailable', status: 0 };
    }
    if (reply.status >= 200 && reply.status < 300) {
      const data = await readJson(reply);
      return data === undefined
        ? { ok: false, failure: 'error', status: reply.status }
        : { ok: true, status: reply.status, data };
    }
    return { ok: false, failure: await classify(reply), status: reply.status };
  }
}

async function classify(reply: Response): Promise<ShopFailure> {
  switch (reply.status) {
    case 401:
      return 'unauthorized';
    case 403:
      return 'forbidden';
    case 404:
      return 'not_found';
    case 409: {
      const body = await readJson(reply);
      const detail = typeof body === 'object' && body !== null ? (body as { detail?: unknown }).detail : null;
      return (typeof detail === 'string' && CONFLICTS[detail]) || 'conflict';
    }
    case 400:
    case 413:
    case 422:
      return 'invalid';
    case 502:
    case 503:
    case 504:
      return 'unavailable';
    default:
      return 'error';
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}
