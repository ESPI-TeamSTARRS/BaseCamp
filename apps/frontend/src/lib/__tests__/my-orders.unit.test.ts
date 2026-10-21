import { describe, expect, it, vi } from 'vitest';
import { fetchMyOrders } from '../my-orders';

const apiOrder = {
  id: '0f1e2d3c-0000-4000-8000-000000000001',
  number: 'BC-ABCDEFGHJK',
  status: 'paid',
  lines: [{ name: 'Popote', unit_price_cents: 3900, quantity: 2, line_total_cents: 7800 }],
  subtotal_cents: 7800,
  shipping_cents: 0,
  total_cents: 7800,
  created_at: '2026-10-21T09:30:00Z',
};

function reply(status: number, body: unknown): typeof fetch {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe('fetchMyOrders', () => {
  it('lit les commandes du compte avec le jeton d acces et sans cache', async () => {
    const fetchImpl = reply(200, { items: [apiOrder], total: 1, limit: 20, offset: 0 });

    const result = await fetchMyOrders('jeton.signe.x', fetchImpl);

    expect(result).toEqual({
      ok: true,
      total: 1,
      orders: [
        {
          id: apiOrder.id,
          number: 'BC-ABCDEFGHJK',
          status: 'paid',
          statusLabel: 'Payée',
          lines: [{ name: 'Popote', unitPriceEur: 39, quantity: 2, lineTotalEur: 78 }],
          subtotalEur: 78,
          shippingEur: 0,
          totalEur: 78,
          createdAt: '2026-10-21T09:30:00Z',
        },
      ],
    });
    const [url, init] = (fetchImpl as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/shop/me/orders?limit=20&offset=0');
    expect(init.headers.Authorization).toBe('Bearer jeton.signe.x');
    expect(init.cache).toBe('no-store');
  });

  it('renvoie une liste vide pour un compte sans commande', async () => {
    const result = await fetchMyOrders('jeton', reply(200, { items: [], total: 0, limit: 20, offset: 0 }));

    expect(result).toEqual({ ok: true, orders: [], total: 0 });
  });

  it('distingue la session a rouvrir (401) du service indisponible', async () => {
    expect(await fetchMyOrders('x', reply(401, { detail: 'Authentification requise.' }))).toEqual({
      ok: false,
      reason: 'unauthenticated',
    });
    for (const status of [403, 500, 503]) {
      expect(await fetchMyOrders('x', reply(status, {}))).toEqual({ ok: false, reason: 'unavailable' });
    }
  });

  it('traite un corps inattendu et une panne reseau comme indisponibles', async () => {
    expect(await fetchMyOrders('x', reply(200, { items: 'non' }))).toEqual({
      ok: false,
      reason: 'unavailable',
    });
    const down = vi.fn().mockRejectedValue(new Error('reseau')) as unknown as typeof fetch;
    expect(await fetchMyOrders('x', down)).toEqual({ ok: false, reason: 'unavailable' });
  });

  it('donne un libelle neutre a un statut inconnu', async () => {
    const result = await fetchMyOrders(
      'x',
      reply(200, { items: [{ ...apiOrder, status: 'nouveau_statut' }], total: 1 })
    );

    expect(result.ok && result.orders[0].statusLabel).toBe('Statut en cours de mise à jour');
  });
});
