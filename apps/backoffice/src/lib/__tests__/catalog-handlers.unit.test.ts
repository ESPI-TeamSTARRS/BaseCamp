import { describe, expect, it } from 'vitest';
import { handleCatalog, readCookie, type CatalogAction } from '../handlers/catalog-handlers';
import type { LogEvent } from '../log-event';
import type { ShopCall, ShopReply } from '../shop-client';

const PRODUCT = { id: 'prd_1', name: 'Tente Tunnel', version: 3 };

function setup(reply: ShopReply = { ok: true, status: 200, data: PRODUCT }) {
  const calls: ShopCall[] = [];
  const events: LogEvent[] = [];
  const deps = {
    shop: {
      call: async (call: ShopCall) => {
        calls.push(call);
        return reply;
      },
    },
    log: (event: LogEvent) => events.push(event),
  };
  return { calls, events, deps };
}

function request(
  method: string,
  url = 'http://backoffice:3000/bff/products',
  options: { body?: BodyInit; headers?: Record<string, string>; cookie?: string | null } = {}
): Request {
  const headers: Record<string, string> = {
    host: 'admin.localhost',
    'sec-fetch-site': 'same-origin',
    ...options.headers,
  };
  if (options.cookie !== null) headers.cookie = options.cookie ?? 'bo_access=jeton.secret.x';
  return new Request(url, { method, headers, body: options.body });
}

async function run(action: CatalogAction, req: Request, deps: ReturnType<typeof setup>['deps'], id?: string) {
  const response = await handleCatalog(req, action, id, deps);
  return { response, body: await response.json() };
}

describe('handleCatalog – lecture', () => {
  it('liste avec la recherche, la pagination et le filtre des archivés relayés à shop', async () => {
    const { calls, deps } = setup();

    const { response, body } = await run(
      'list',
      request(
        'GET',
        'http://backoffice:3000/bff/products?limit=20&offset=40&include_archived=true&q=%20tunnel%20'
      ),
      deps
    );

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(body).toEqual(PRODUCT);
    expect(calls[0]).toMatchObject({
      method: 'GET',
      path: '/admin/products?limit=20&offset=40&include_archived=true&q=tunnel',
      token: 'jeton.secret.x',
    });
  });

  it('liste sans paramètre', async () => {
    const { calls, deps } = setup();

    await run('list', request('GET'), deps);

    expect(calls[0].path).toBe('/admin/products');
  });

  it.each([
    'limit=0',
    'limit=101',
    'limit=abc',
    'offset=-1',
    'offset=99999999',
    'include_archived=oui',
    `q=${'x'.repeat(101)}`,
  ])('refuse le paramètre %s avant tout appel', async (query) => {
    const { calls, deps } = setup();

    const { response } = await run(
      'list',
      request('GET', `http://backoffice:3000/bff/products?${query}`),
      deps
    );

    expect(response.status).toBe(400);
    expect(calls).toEqual([]);
  });

  it('ignore une recherche vide', async () => {
    const { calls, deps } = setup();

    await run('list', request('GET', 'http://backoffice:3000/bff/products?q=%20%20'), deps);

    expect(calls[0].path).toBe('/admin/products');
  });

  it('lit un produit', async () => {
    const { calls, deps } = setup();

    await run('get', request('GET', 'http://backoffice:3000/bff/products/prd_1'), deps, 'prd_1');

    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/products/prd_1' });
  });

  it('refuse un identifiant mal formé', async () => {
    const { calls, deps } = setup();

    const { response } = await run('get', request('GET'), deps, '../auth');

    expect(response.status).toBe(400);
    expect(calls).toEqual([]);
  });
});

describe('handleCatalog – écritures', () => {
  it('crée un produit en relayant le JSON et le statut 201', async () => {
    const { calls, deps } = setup({ ok: true, status: 201, data: PRODUCT });

    const { response } = await run(
      'create',
      request('POST', undefined, {
        body: JSON.stringify({ name: 'Tente' }),
        headers: { 'content-type': 'application/json' },
      }),
      deps
    );

    expect(response.status).toBe(201);
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/admin/products', json: { name: 'Tente' } });
  });

  it('modifie, archive et téléverse une image', async () => {
    const { calls, deps } = setup();

    await run('update', request('PATCH', undefined, { body: '{"version":3,"stock":4}' }), deps, 'prd_1');
    await run('archive', request('POST', undefined, { body: '' }), deps, 'prd_1');
    await run(
      'image',
      request('POST', undefined, { body: new Uint8Array([137, 80, 78, 71]) }),
      deps,
      'prd_1'
    );

    expect(calls.map((c) => [c.method, c.path])).toEqual([
      ['PATCH', '/admin/products/prd_1'],
      ['POST', '/admin/products/prd_1/archive'],
      ['POST', '/admin/products/prd_1/image'],
    ]);
    expect(calls[0].json).toEqual({ version: 3, stock: 4 });
    expect(Array.from(calls[2].bytes ?? [])).toEqual([137, 80, 78, 71]);
  });

  it.each(['create', 'update', 'archive', 'image'] as const)(
    'refuse un %s venu d’un autre site, sans appeler shop',
    async (action) => {
      const { calls, deps } = setup();

      const { response, body } = await run(
        action,
        request('POST', undefined, { headers: { 'sec-fetch-site': 'cross-site' }, body: '{}' }),
        deps,
        'prd_1'
      );

      expect(response.status).toBe(403);
      expect(body.code).toBe('cross_origin');
      expect(calls).toEqual([]);
    }
  );

  it.each([['pas du json'], ['[1,2]'], ['"texte"']])('refuse le corps %s', async (text) => {
    const { calls, deps } = setup();

    const { response } = await run('create', request('POST', undefined, { body: text }), deps);

    expect(response.status).toBe(400);
    expect(calls).toEqual([]);
  });

  it('refuse un JSON trop volumineux', async () => {
    const { calls, deps } = setup();

    const { response } = await run(
      'update',
      request('PATCH', undefined, { body: JSON.stringify({ description: 'x'.repeat(70_000) }) }),
      deps,
      'prd_1'
    );

    expect(response.status).toBe(413);
    expect(calls).toEqual([]);
  });

  it('refuse une image de plus de 2 Mio, déclarée ou non, avec un message clair', async () => {
    const { calls, deps } = setup();
    const declared = request('POST', undefined, {
      body: 'x',
      headers: { 'content-length': String(2 * 1024 * 1024 + 1) },
    });
    const streamed = request('POST', undefined, { body: new Uint8Array(2 * 1024 * 1024 + 1) });

    for (const req of [declared, streamed]) {
      const { response, body } = await run('image', req, deps, 'prd_1');
      expect(response.status).toBe(413);
      expect(body.detail).toBe('Image refusée : JPEG, PNG ou WebP, 2 Mo au plus.');
    }
    expect(calls).toEqual([]);
  });
});

describe('handleCatalog – échecs', () => {
  it('sans cookie de session : 401 et cookie effacé', async () => {
    const { calls, deps } = setup();

    const { response, body } = await run('list', request('GET', undefined, { cookie: null }), deps);

    expect(response.status).toBe(401);
    expect(body.code).toBe('unauthorized');
    expect(calls).toEqual([]);
    expect(response.headers.getSetCookie().join()).toMatch(/Max-Age=0/i);
  });

  it.each([
    ['unauthorized', 401, 'Session expirée. Reconnectez-vous.'],
    ['forbidden', 403, 'Accès refusé.'],
    ['not_found', 404, 'Produit introuvable.'],
    [
      'stale_version',
      409,
      'Ce produit a été modifié ailleurs depuis son ouverture. Rechargez-le pour voir la dernière version.',
    ],
    ['archived', 409, 'Ce produit est archivé et ne peut plus être modifié.'],
    ['duplicate', 409, 'Un produit portant cet identifiant existe déjà.'],
    ['too_many_images', 409, 'Le nombre maximal d’images est atteint.'],
    ['conflict', 409, 'Conflit : l’opération n’a pas pu être appliquée.'],
    ['invalid', 422, 'Les données envoyées sont refusées.'],
    ['unavailable', 503, 'Le catalogue est momentanément indisponible. Réessayez dans un instant.'],
    ['error', 502, 'Une erreur est survenue. Réessayez.'],
  ] as const)('traduit « %s » en %i avec un message fixe', async (failure, status, detail) => {
    const { events, deps } = setup({ ok: false, failure, status: 418 });

    const { response, body } = await run('get', request('GET'), deps, 'prd_1');

    expect(response.status).toBe(status);
    expect(body).toEqual({ detail, code: failure });
    expect(events[0]).toMatchObject({ event: 'backoffice.catalog_get', reason: failure });
  });

  it('un refus de forme sur une image donne le message d’image', async () => {
    const { deps } = setup({ ok: false, failure: 'invalid', status: 422 });

    const { body } = await run(
      'image',
      request('POST', undefined, { body: new Uint8Array([1]) }),
      deps,
      'prd_1'
    );

    expect(body.detail).toBe('Image refusée : JPEG, PNG ou WebP, 2 Mo au plus.');
  });
});

describe('handleCatalog – journal', () => {
  it('journalise une ligne par appel, sans jeton ni donnée produit', async () => {
    const { events, deps } = setup();

    await run(
      'update',
      request('PATCH', undefined, {
        body: '{"version":1,"name":"Secret"}',
        headers: { 'x-correlation-id': 'corr-12345678' },
      }),
      deps,
      'prd_1'
    );

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      event: 'backoffice.catalog_update',
      outcome: 'success',
      correlation_id: 'corr-12345678',
    });
    const line = JSON.stringify(events[0]);
    expect(line).not.toContain('jeton.secret.x');
    expect(line).not.toContain('Secret');
  });

  it('classe l’indisponibilité en erreur et les refus en denied', async () => {
    const down = setup({ ok: false, failure: 'unavailable', status: 0 });
    const refused = setup({ ok: false, failure: 'stale_version', status: 409 });

    await run('get', request('GET'), down.deps, 'prd_1');
    await run('get', request('GET'), refused.deps, 'prd_1');

    expect(down.events[0].outcome).toBe('error');
    expect(refused.events[0].outcome).toBe('denied');
  });
});

describe('readCookie', () => {
  it('retient la valeur du cookie demandé parmi plusieurs', () => {
    const req = new Request('http://x/', { headers: { cookie: 'a=1; bo_access=x=y.z; b=2' } });

    expect(readCookie(req, 'bo_access')).toBe('x=y.z');
    expect(readCookie(req, 'absent')).toBeUndefined();
    expect(readCookie(new Request('http://x/'), 'a')).toBeUndefined();
  });
});
