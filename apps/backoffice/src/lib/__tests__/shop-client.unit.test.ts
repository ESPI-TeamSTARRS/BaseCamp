import { describe, expect, it } from 'vitest';
import { ShopClient, type ShopCall } from '../shop-client';

const CALL: ShopCall = {
  method: 'GET',
  path: '/admin/products',
  token: 'jeton.secret.x',
  correlationId: 'corr-12345678',
};

function client(reply: Response | Error, seen: Array<[string, RequestInit]> = []) {
  return new ShopClient('http://shop:8000', async (url, init) => {
    seen.push([String(url), init ?? {}]);
    if (reply instanceof Error) throw reply;
    return reply;
  });
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('ShopClient', () => {
  it('appelle shop avec le jeton en Bearer, l’identifiant de corrélation et sans redirection', async () => {
    const seen: Array<[string, RequestInit]> = [];

    const reply = await client(json(200, { items: [] }), seen).call(CALL);

    expect(reply).toEqual({ ok: true, status: 200, data: { items: [] } });
    const [url, init] = seen[0];
    expect(url).toBe('http://shop:8000/admin/products');
    const headers = init.headers as Headers;
    expect(headers.get('authorization')).toBe('Bearer jeton.secret.x');
    expect(headers.get('x-correlation-id')).toBe('corr-12345678');
    expect(init.redirect).toBe('error');
  });

  it('envoie un corps JSON ou des octets bruts selon l’appel', async () => {
    const seen: Array<[string, RequestInit]> = [];
    const shop = client(json(200, {}), seen);

    await shop.call({ ...CALL, method: 'POST', json: { name: 'Tente' } });
    await shop.call({ ...CALL, method: 'POST', bytes: new Uint8Array([1, 2, 3]) });

    expect((seen[0][1].headers as Headers).get('content-type')).toBe('application/json');
    expect(seen[0][1].body).toBe('{"name":"Tente"}');
    expect((seen[1][1].headers as Headers).get('content-type')).toBe('application/octet-stream');
    expect(seen[1][1].body).toBeInstanceOf(Uint8Array);
  });

  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [422, 'invalid'],
    [413, 'invalid'],
    [503, 'unavailable'],
    [500, 'error'],
  ])('classe un %i comme %s sans rien refléter du corps', async (status, failure) => {
    const reply = await client(json(status, { detail: 'secret interne' })).call(CALL);

    expect(reply).toEqual({ ok: false, failure, status });
  });

  it.each([
    ['Version perimee.', 'stale_version'],
    ['Produit archive.', 'archived'],
    ['Produit deja existant.', 'duplicate'],
    ["Nombre maximal d'images atteint.", 'too_many_images'],
    ['autre chose', 'conflict'],
  ])('distingue le conflit « %s »', async (detail, failure) => {
    const reply = await client(json(409, { detail })).call(CALL);

    expect(reply).toMatchObject({ ok: false, failure, status: 409 });
  });

  it('classe un 409 sans corps lisible comme un conflit générique', async () => {
    const reply = await client(new Response('pas du json', { status: 409 })).call(CALL);

    expect(reply).toMatchObject({ ok: false, failure: 'conflict' });
  });

  it('classe un réseau coupé comme indisponible', async () => {
    expect(await client(new Error('ECONNREFUSED')).call(CALL)).toEqual({
      ok: false,
      failure: 'unavailable',
      status: 0,
    });
  });

  it('refuse une réponse de succès qui n’est pas du JSON', async () => {
    const reply = await client(new Response('<html>', { status: 200 })).call(CALL);

    expect(reply).toEqual({ ok: false, failure: 'error', status: 200 });
  });
});
