import { describe, expect, it, vi } from 'vitest';
import { isOrderNumber, lookupOrder, orderStatusLabel } from '../order-lookup';

const apiOrder = {
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

describe('isOrderNumber', () => {
  it('accepte le format BC- suivi de 10 caractères et refuse le reste', () => {
    expect(isOrderNumber('BC-ABCDEFGHJK')).toBe(true);
    expect(isOrderNumber('BC-ABC')).toBe(false);
    expect(isOrderNumber("' OR '1'='1")).toBe(false);
    expect(isOrderNumber('')).toBe(false);
  });
});

describe('orderStatusLabel', () => {
  it('traduit les statuts connus et reste neutre sur un statut inconnu', () => {
    expect(orderStatusLabel('pending_payment')).toBe('En attente de paiement');
    expect(orderStatusLabel('paid')).toBe('Payée');
    expect(orderStatusLabel('expired')).toBe('Expirée');
    expect(orderStatusLabel('refunded')).toBe('Remboursée');
    expect(orderStatusLabel('autre')).toBe('Statut en cours de mise à jour');
  });
});

describe('lookupOrder', () => {
  it('envoie le numéro et l’email normalisés et renvoie la commande en euros', async () => {
    const fetchImpl = reply(200, apiOrder);

    const result = await lookupOrder(' bc-abcdefghjk ', '  Camille@Example.org ', fetchImpl);

    expect(result).toEqual({
      ok: true,
      order: {
        number: 'BC-ABCDEFGHJK',
        status: 'paid',
        statusLabel: 'Payée',
        lines: [{ name: 'Popote', unitPriceEur: 39, quantity: 2, lineTotalEur: 78 }],
        subtotalEur: 78,
        shippingEur: 0,
        totalEur: 78,
        createdAt: '2026-10-21T09:30:00Z',
      },
    });
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/shop/orders/lookup');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ orderNumber: 'BC-ABCDEFGHJK', email: 'Camille@Example.org' });
  });

  it("n'appelle pas le serveur si le numéro n'a pas le bon format", async () => {
    const fetchImpl = reply(200, apiOrder);

    expect(await lookupOrder('nimporte quoi', 'a@b.fr', fetchImpl)).toEqual({ ok: false, reason: 'invalid' });
    expect(await lookupOrder('BC-ABCDEFGHJK', 'pas-un-email', fetchImpl)).toEqual({
      ok: false,
      reason: 'invalid',
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('une commande introuvable ou un email faux donnent le même résultat', async () => {
    expect(
      await lookupOrder('BC-ABCDEFGHJK', 'a@b.fr', reply(404, { detail: 'Commande introuvable.' }))
    ).toEqual({
      ok: false,
      reason: 'not_found',
    });
  });

  it('signale le service indisponible sur 429, 5xx, erreur réseau ou réponse inattendue', async () => {
    const failing = vi.fn().mockRejectedValue(new Error('réseau')) as unknown as typeof fetch;
    for (const fetchImpl of [reply(429, {}), reply(503, {}), failing, reply(200, { nope: true })]) {
      expect(await lookupOrder('BC-ABCDEFGHJK', 'a@b.fr', fetchImpl)).toEqual({
        ok: false,
        reason: 'unavailable',
      });
    }
  });

  it('traduit un 422 du serveur en saisie invalide', async () => {
    expect(await lookupOrder('BC-ABCDEFGHJK', 'a@b.fr', reply(422, {}))).toEqual({
      ok: false,
      reason: 'invalid',
    });
  });
});
