import { describe, expect, it } from 'vitest';
import { handleOrders, type OrderAction, type OrderDeps } from '../handlers/order-handlers';
import type { LogEvent } from '../log-event';
import { pseudonymize } from '../pseudonym';
import type { EvaluateResult } from '../session-service';
import type { ShopCall, ShopReply } from '../shop-client';

const KEY = 'cle-de-test';
const OPERATOR_ID = '0b6c1a52-7a3e-4f0e-9b57-3f2d8c6a1e90';
const ORDER_ID = '00000000-0000-4000-8000-000000000001';
const ORDER = {
  id: ORDER_ID,
  number: 'BC-1001',
  status: 'paid',
  email: 'camille.martin@example.org',
  shipping_address: { line1: '12 rue des Alpes' },
};
const VALID: EvaluateResult = {
  kind: 'valid',
  claims: { sub: OPERATOR_ID, exp: 9_999_999_999, roles: ['operator'], amr: ['pwd', 'face'] },
};

function setup(reply: ShopReply = { ok: true, status: 200, data: ORDER }, session: EvaluateResult = VALID) {
  const calls: ShopCall[] = [];
  const events: LogEvent[] = [];
  const seen: (string | undefined)[] = [];
  const deps: OrderDeps = {
    shop: {
      call: async (call: ShopCall) => {
        calls.push(call);
        return reply;
      },
    },
    sessions: {
      evaluate: async (token: string | undefined) => {
        seen.push(token);
        return session;
      },
    },
    pseudonymKey: KEY,
    log: (event: LogEvent) => events.push(event),
  };
  return { calls, events, seen, deps };
}

function request(
  url = 'http://backoffice:3000/bff/orders',
  options: { headers?: Record<string, string>; cookie?: string | null; method?: string } = {}
): Request {
  const headers: Record<string, string> = { host: 'mercure.localhost', ...options.headers };
  if (options.cookie !== null) headers.cookie = options.cookie ?? 'bo_access=jeton.secret.x';
  return new Request(url, { method: options.method ?? 'GET', headers });
}

async function run(action: OrderAction, req: Request, deps: OrderDeps, id?: string) {
  const response = await handleOrders(req, action, id, deps);
  return { response, body: await response.json() };
}

describe('handleOrders : liste', () => {
  it('relaie pagination, statut et recherche à shop avec le jeton du cookie', async () => {
    const { calls, deps } = setup();

    const { response, body } = await run(
      'list',
      request('http://backoffice:3000/bff/orders?limit=20&offset=40&status=paid&q=%20BC-10%20'),
      deps
    );

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(body).toEqual(ORDER);
    expect(calls[0]).toMatchObject({
      method: 'GET',
      path: '/admin/orders?limit=20&offset=40&status=paid&q=BC-10',
      token: 'jeton.secret.x',
    });
  });

  it('liste sans paramètre', async () => {
    const { calls, deps } = setup();

    await run('list', request(), deps);

    expect(calls[0].path).toBe('/admin/orders');
  });

  it.each([
    'limit=0',
    'limit=101',
    'limit=abc',
    'offset=-1',
    'offset=99999999',
    'status=shipped',
    `q=${'x'.repeat(101)}`,
  ])('refuse le paramètre %s avant tout appel', async (query) => {
    const { calls, deps } = setup();

    const { response, body } = await run('list', request(`http://backoffice:3000/bff/orders?${query}`), deps);

    expect(response.status).toBe(400);
    expect(body).toEqual({ detail: 'Requête invalide.', code: 'bad_request' });
    expect(calls).toHaveLength(0);
  });

  it('journalise la liste sans la recherche ni donnée personnelle', async () => {
    const { events, deps } = setup();

    await run('list', request('http://backoffice:3000/bff/orders?q=camille%40example.org'), deps);

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ event: 'backoffice.orders_list', outcome: 'success' });
    expect(JSON.stringify(events)).not.toContain('camille');
  });
});

describe('handleOrders : détail', () => {
  it('relaie la lecture et renvoie la commande telle que shop la rend', async () => {
    const { calls, deps } = setup();

    const { response, body } = await run('get', request(), deps, ORDER_ID);

    expect(response.status).toBe(200);
    expect(body).toEqual(ORDER);
    expect(calls[0]).toMatchObject({ method: 'GET', path: `/admin/orders/${ORDER_ID}` });
  });

  it('émet backoffice.order_view avec l’opérateur pseudonymisé, sans e-mail ni adresse', async () => {
    const { events, deps } = setup();

    await run(
      'get',
      request(undefined, { headers: { 'x-correlation-id': 'corr-12345678' } }),
      deps,
      ORDER_ID
    );

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      event: 'backoffice.order_view',
      outcome: 'success',
      level: 'info',
      correlation_id: 'corr-12345678',
      resource_type: 'order',
      resource_id: ORDER_ID,
      actor_type: 'user',
      actor_id: pseudonymize(OPERATOR_ID, KEY),
    });
    const raw = JSON.stringify(events);
    expect(raw).not.toContain('camille');
    expect(raw).not.toContain('rue des Alpes');
    expect(raw).not.toContain('jeton.secret.x');
    expect(raw).not.toContain(OPERATOR_ID);
  });

  it('une commande introuvable est refusée avec un message fixe, et journalisée', async () => {
    const { events, deps } = setup({ ok: false, failure: 'not_found', status: 404 });

    const { response, body } = await run('get', request(), deps, ORDER_ID);

    expect(response.status).toBe(404);
    expect(body).toEqual({ detail: 'Commande introuvable.', code: 'not_found' });
    expect(events[0]).toMatchObject({
      event: 'backoffice.order_view',
      outcome: 'denied',
      reason: 'not_found',
      actor_id: pseudonymize(OPERATOR_ID, KEY),
    });
  });

  it.each(['..%2Fadmin', 'a b', 'x'.repeat(65)])('refuse l’identifiant %s', async (id) => {
    const { calls, deps } = setup();

    const { response } = await run('get', request(), deps, decodeURIComponent(id));

    expect(response.status).toBe(400);
    expect(calls).toHaveLength(0);
  });
});

describe('handleOrders : accès', () => {
  it.each<[OrderAction, string | undefined]>([
    ['list', undefined],
    ['get', ORDER_ID],
  ])('%s sans cookie : 401, aucun appel à shop', async (action, id) => {
    const { calls, seen, deps } = setup();

    const { response, body } = await run(action, request(undefined, { cookie: null }), deps, id);

    expect(response.status).toBe(401);
    expect(body).toEqual({ detail: 'Session expirée. Reconnectez-vous.', code: 'unauthorized' });
    expect(response.headers.get('set-cookie')).toContain('bo_access=');
    expect(calls).toHaveLength(0);
    expect(seen).toHaveLength(0);
  });

  it.each(['no_session', 'session_expired', 'bad_signature', 'unknown_key'])(
    'un jeton invalide (%s) : 401 sans appel à shop',
    async (reason) => {
      const { calls, deps } = setup(undefined, { kind: 'none', reason });

      const { response } = await run('get', request(), deps, ORDER_ID);

      expect(response.status).toBe(401);
      expect(calls).toHaveLength(0);
    }
  );

  it.each(['not_operator', 'second_factor_missing'])(
    'sans le rôle opérateur ou le visage (%s) : 403 sans appel à shop',
    async (reason) => {
      const { calls, events, deps } = setup(undefined, { kind: 'none', reason });

      const { response, body } = await run('list', request(), deps);

      expect(response.status).toBe(403);
      expect(body).toEqual({ detail: 'Accès refusé.', code: 'forbidden' });
      expect(calls).toHaveLength(0);
      expect(events[0]).toMatchObject({ outcome: 'denied', reason: 'forbidden' });
    }
  );

  it('auth injoignable : 503 sans appel à shop', async () => {
    const { calls, deps } = setup(undefined, { kind: 'error', reason: 'auth_unavailable' });

    const { response, body } = await run('get', request(), deps, ORDER_ID);

    expect(response.status).toBe(503);
    expect(body.code).toBe('unavailable');
    expect(calls).toHaveLength(0);
  });
});

describe('handleOrders : échecs de shop', () => {
  it.each([
    ['unauthorized', 401, 'Session expirée. Reconnectez-vous.'],
    ['forbidden', 403, 'Accès refusé.'],
    ['not_found', 404, 'Commande introuvable.'],
    ['invalid', 422, 'Les données envoyées sont refusées.'],
    ['unavailable', 503, 'Les commandes sont momentanément indisponibles. Réessayez dans un instant.'],
    ['error', 502, 'Une erreur est survenue. Réessayez.'],
  ] as const)('%s -> %i et message fixe', async (failure, status, detail) => {
    const { events, deps } = setup({ ok: false, failure, status: 0 });

    const { response, body } = await run('list', request(), deps);

    expect(response.status).toBe(status);
    expect(body).toEqual({ detail, code: failure });
    expect(events[0]).toMatchObject({
      event: 'backoffice.orders_list',
      outcome: failure === 'unavailable' || failure === 'error' ? 'error' : 'denied',
      reason: failure,
    });
  });

  it('ne renvoie jamais le jeton ni le texte de shop', async () => {
    const { deps } = setup({ ok: false, failure: 'error', status: 500 });

    const { response, body } = await run('get', request(), deps, ORDER_ID);

    expect(JSON.stringify(body)).not.toContain('jeton.secret.x');
    expect(Object.keys(body).sort()).toEqual(['code', 'detail']);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });
});
