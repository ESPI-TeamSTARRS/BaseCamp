import { describe, expect, it, vi } from 'vitest';
import { IdempotencyKeys, placeOrder, toOrderRequest } from '../place-order';
import { SHIPPING_COUNTRIES, validateOrderForm, type OrderForm } from '../order-form';
import type { CartLine } from '../cart-lines';

const product = {
  id: 'popote',
  slug: 'popote',
  name: 'Popote',
  priceEur: 39,
  images: ['/media/p.svg'],
  availability: 'in_stock' as const,
};
const lines: CartLine[] = [{ product, quantity: 2 }];
const form: OrderForm = {
  email: 'camille.martin@example.org',
  fullName: 'Camille Martin',
  line1: '12 rue des Alpes',
  line2: '',
  postalCode: '38000',
  city: 'Grenoble',
  country: 'FR',
};

const apiOrder = {
  id: 'o-1',
  number: 'BC-ABCDEFGHJK',
  status: 'pending_payment',
  email: form.email,
  shipping_address: {
    full_name: 'Camille Martin',
    line1: '12 rue des Alpes',
    line2: null,
    postal_code: '38000',
    city: 'Grenoble',
    country: 'FR',
  },
  lines: [
    { product_id: 'popote', name: 'Popote', unit_price_cents: 3900, quantity: 2, line_total_cents: 7800 },
  ],
  subtotal_cents: 7800,
  shipping_cents: 590,
  total_cents: 8390,
  created_at: '2026-10-20T12:00:00Z',
};

function reply(status: number, body: unknown): typeof fetch {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe('validateOrderForm', () => {
  it('accepte un formulaire complet et nettoie les espaces', () => {
    const result = validateOrderForm({ ...form, fullName: '  Camille Martin ', line2: '  ' });
    expect(result).toEqual({ ok: true, form: { ...form, line2: '' } });
  });

  it('liste exactement les sept pays livrés', () => {
    expect([...SHIPPING_COUNTRIES.map((c) => c.code)].sort()).toEqual([
      'BE',
      'CH',
      'DE',
      'ES',
      'FR',
      'IT',
      'LU',
    ]);
  });

  it.each([
    ['email', { email: 'pas-un-email' }],
    ['fullName', { fullName: '' }],
    ['line1', { line1: ' ' }],
    ['postalCode', { postalCode: '' }],
    ['city', { city: '' }],
    ['country', { country: 'US' }],
  ])('refuse le champ %s invalide avec un message en français', (field, override) => {
    const result = validateOrderForm({ ...form, ...override });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(Object.keys(result.errors)).toEqual([field]);
      expect(result.errors[field as keyof OrderForm]).toMatch(/\S/);
    }
  });
});

describe('toOrderRequest', () => {
  it("n'envoie que l'identifiant et la quantité des produits, jamais un prix", () => {
    const request = toOrderRequest(lines, form);
    expect(request.lines).toEqual([{ productId: 'popote', quantity: 2 }]);
    expect(JSON.stringify(request)).not.toMatch(/price|prix/i);
    expect(request.shippingAddress).toEqual({
      fullName: 'Camille Martin',
      line1: '12 rue des Alpes',
      postalCode: '38000',
      city: 'Grenoble',
      country: 'FR',
    });
  });

  it("n'envoie line2 que s'il est renseigné", () => {
    expect(toOrderRequest(lines, { ...form, line2: 'Bât B' }).shippingAddress.line2).toBe('Bât B');
  });
});

describe('placeOrder', () => {
  it('crée la commande, envoie la clé d’idempotence et renvoie le numéro et le total', async () => {
    const fetchImpl = reply(201, apiOrder);
    const result = await placeOrder(lines, form, 'cle-12345678', fetchImpl);

    expect(result).toEqual({
      ok: true,
      order: { id: 'o-1', number: 'BC-ABCDEFGHJK', totalEur: 83.9, replayed: false },
    });
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/shop/orders');
    expect(init.method).toBe('POST');
    expect(init.headers['Idempotency-Key']).toBe('cle-12345678');
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('signale un rejeu quand le serveur répond 200', async () => {
    const result = await placeOrder(lines, form, 'cle-12345678', reply(200, apiOrder));
    expect(result).toMatchObject({ ok: true, order: { replayed: true } });
  });

  it('traduit un 409 en stock insuffisant', async () => {
    const result = await placeOrder(lines, form, 'cle-12345678', reply(409, { detail: 'x' }));
    expect(result).toEqual({ ok: false, reason: 'stock' });
  });

  it('traduit un 422 en commande refusée avec le message fixe du serveur', async () => {
    const result = await placeOrder(
      lines,
      form,
      'cle-12345678',
      reply(422, { detail: 'Pays de livraison non pris en charge.' })
    );
    expect(result).toEqual({
      ok: false,
      reason: 'invalid',
      message: 'Pays de livraison non pris en charge.',
    });
  });

  it('retombe sur un message générique si le 422 n’a pas de détail texte', async () => {
    const result = await placeOrder(
      lines,
      form,
      'cle-12345678',
      reply(422, { detail: 'Requete invalide.', fields: ['x'] })
    );
    expect(result).toMatchObject({ ok: false, reason: 'invalid' });
  });

  it('signale le service indisponible sur erreur réseau, 5xx ou réponse inattendue', async () => {
    const failing = vi.fn().mockRejectedValue(new Error('réseau')) as unknown as typeof fetch;
    expect(await placeOrder(lines, form, 'cle-12345678', failing)).toEqual({
      ok: false,
      reason: 'unavailable',
    });
    expect(await placeOrder(lines, form, 'cle-12345678', reply(500, {}))).toEqual({
      ok: false,
      reason: 'unavailable',
    });
    expect(await placeOrder(lines, form, 'cle-12345678', reply(201, { nope: true }))).toEqual({
      ok: false,
      reason: 'unavailable',
    });
  });
});

describe('IdempotencyKeys', () => {
  it('réutilise la même clé tant que le contenu est identique (rejeu sûr après un échec réseau)', () => {
    const keys = new IdempotencyKeys(() => 'cle-' + Math.random().toString(36).slice(2, 12));
    const first = keys.keyFor(lines, form);
    expect(keys.keyFor(lines, form)).toBe(first);
  });

  it('change de clé dès que le panier ou le formulaire change', () => {
    const keys = new IdempotencyKeys(() => 'cle-' + Math.random().toString(36).slice(2, 12));
    const first = keys.keyFor(lines, form);
    expect(keys.keyFor([{ product, quantity: 3 }], form)).not.toBe(first);
    expect(keys.keyFor(lines, { ...form, city: 'Lyon' })).not.toBe(first);
  });
});
