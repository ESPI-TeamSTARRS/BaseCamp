import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { catalogApi } from '../api';
import * as navigation from '../navigation';

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  vi.spyOn(navigation, 'redirectToLogin').mockImplementation(() => undefined);
});
afterEach(() => {
  fetchMock.mockReset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }));
}

describe('catalogApi', () => {
  it('liste avec pagination, recherche et filtre des archivés', async () => {
    reply(200, { items: [], total: 0, limit: 20, offset: 40 });

    const result = await catalogApi.list({ q: ' tente ', includeArchived: true, offset: 40, limit: 20 });

    expect(result).toEqual({ ok: true, data: { items: [], total: 0, limit: 20, offset: 40 } });
    expect(fetchMock.mock.calls[0][0]).toBe('/bff/products?limit=20&offset=40&include_archived=true&q=tente');
  });

  it('omet la recherche vide et le filtre inactif', async () => {
    reply(200, {});

    await catalogApi.list({ q: '  ', includeArchived: false, offset: 0, limit: 20 });

    expect(fetchMock.mock.calls[0][0]).toBe('/bff/products?limit=20&offset=0');
  });

  it('crée, modifie, archive et lit', async () => {
    reply(201, { id: 'a' });
    reply(200, { id: 'a' });
    reply(200, { id: 'a' });
    reply(200, { id: 'a' });

    await catalogApi.create({ name: 'A' });
    await catalogApi.update('a b', { version: 1 });
    await catalogApi.archive('a');
    await catalogApi.get('a');

    const calls = fetchMock.mock.calls.map(([url, init]) => [url, init?.method ?? 'GET']);
    expect(calls).toEqual([
      ['/bff/products', 'POST'],
      ['/bff/products/a%20b', 'PATCH'],
      ['/bff/products/a/archive', 'POST'],
      ['/bff/products/a', 'GET'],
    ]);
    expect(fetchMock.mock.calls[0][1].body).toBe('{"name":"A"}');
  });

  it('envoie le fichier tel quel pour le téléversement', async () => {
    reply(200, { id: 'a' });
    const file = new File([new Uint8Array([1, 2])], 'photo.png', { type: 'image/png' });

    await catalogApi.uploadImage('a', file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/bff/products/a/image');
    expect(init.body).toBe(file);
  });

  it('rend le message fixe et le code du serveur en cas d’échec', async () => {
    reply(409, { detail: 'Ce produit a été modifié ailleurs.', code: 'stale_version' });

    expect(await catalogApi.get('a')).toEqual({
      ok: false,
      status: 409,
      code: 'stale_version',
      detail: 'Ce produit a été modifié ailleurs.',
    });
  });

  it('retourne à la connexion quand la session a expiré', async () => {
    reply(401, { detail: 'Session expirée. Reconnectez-vous.', code: 'unauthorized' });

    const result = await catalogApi.get('a');

    expect(result).toMatchObject({ ok: false, status: 401, code: 'unauthorized' });
    expect(navigation.redirectToLogin).toHaveBeenCalledOnce();
  });

  it('donne un message générique à une réponse illisible', async () => {
    fetchMock.mockResolvedValueOnce(new Response('<html>', { status: 502 }));

    expect(await catalogApi.get('a')).toEqual({
      ok: false,
      status: 502,
      code: 'error',
      detail: 'Une erreur est survenue. Réessayez.',
    });
  });

  it('signale une panne réseau', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    expect(await catalogApi.get('a')).toMatchObject({ ok: false, status: 0, code: 'network' });
  });
});

describe('redirectToLogin', () => {
  it('renvoie le navigateur vers /login', () => {
    const location = { href: '/produits' };
    vi.stubGlobal('window', { location });
    vi.mocked(navigation.redirectToLogin).mockRestore();

    navigation.redirectToLogin();

    expect(location.href).toBe('/login');
  });
});
