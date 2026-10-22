import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as navigation from '../../catalog/navigation';
import { ordersApi } from '../api';
import { formatDateTime, STATUS_LABELS, statusLabel } from '../format';

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

describe('ordersApi', () => {
  it('liste avec pagination, statut et recherche, via /bff/orders', async () => {
    reply(200, { items: [], total: 0, limit: 20, offset: 40 });

    const result = await ordersApi.list({ q: ' BC-10 ', status: 'paid', offset: 40, limit: 20 });

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe('/bff/orders?limit=20&offset=40&status=paid&q=BC-10');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
  });

  it('omet la recherche vide et le statut « tous »', async () => {
    reply(200, {});

    await ordersApi.list({ q: '  ', status: '', offset: 0, limit: 20 });

    expect(fetchMock.mock.calls[0][0]).toBe('/bff/orders?limit=20&offset=0');
  });

  it('lit le détail d’une commande, identifiant encodé', async () => {
    reply(200, { id: 'a b' });

    await ordersApi.get('a b');

    expect(fetchMock.mock.calls[0][0]).toBe('/bff/orders/a%20b');
  });

  it('rend le message fixe du serveur en cas d’échec', async () => {
    reply(404, { detail: 'Commande introuvable.', code: 'not_found' });

    expect(await ordersApi.get('x')).toEqual({
      ok: false,
      status: 404,
      code: 'not_found',
      detail: 'Commande introuvable.',
    });
  });

  it('renvoie à la connexion quand la session a expiré', async () => {
    reply(401, { detail: 'Session expirée. Reconnectez-vous.', code: 'unauthorized' });

    await ordersApi.list({ q: '', status: '', offset: 0, limit: 20 });

    expect(navigation.redirectToLogin).toHaveBeenCalledOnce();
  });

  it('signale une panne réseau', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network'));

    expect(await ordersApi.get('x')).toMatchObject({ ok: false, code: 'network' });
  });
});

describe('format', () => {
  it('nomme chaque statut en français et garde le code inconnu tel quel', () => {
    expect(Object.keys(STATUS_LABELS)).toEqual(['pending_payment', 'paid', 'expired', 'refunded']);
    expect(statusLabel('paid')).toBe('Payée');
    expect(statusLabel('pending_payment')).toBe('En attente de paiement');
    expect(statusLabel('expired')).toBe('Expirée');
    expect(statusLabel('refunded')).toBe('Remboursée');
    expect(statusLabel('autre')).toBe('autre');
  });

  it('date en heure de Paris', () => {
    expect(formatDateTime('2026-10-20T10:00:00Z')).toBe('20 oct. 2026, 12:00');
    expect(formatDateTime('2026-10-20T10:00:00')).toBe('20 oct. 2026, 12:00');
  });

  it('rend le texte reçu quand la date est illisible', () => {
    expect(formatDateTime('pas une date')).toBe('pas une date');
  });
});
