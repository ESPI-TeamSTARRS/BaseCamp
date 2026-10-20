import { describe, expect, it, vi } from 'vitest';
import type { CartLine } from '../cart-lines';
import { fetchCartQuote, toQuoteRequest } from '../cart-quote';

const lines: CartLine[] = [
  {
    product: {
      id: 'tente',
      slug: 'tente',
      name: 'Tente',
      priceEur: 1,
      images: [],
      availability: 'in_stock',
    },
    quantity: 2,
  },
];

const apiQuote = {
  lines: [
    {
      product_id: 'tente',
      name: 'Tente',
      unit_price_cents: 32900,
      quantity: 2,
      line_total_cents: 65800,
      status: 'insufficient_stock',
      available_quantity: 1,
    },
  ],
  subtotal_cents: 65800,
  shipping_cents: 0,
  total_cents: 65800,
  free_shipping_threshold_cents: 8000,
  amount_remaining_for_free_shipping_cents: 0,
  has_issues: true,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('toQuoteRequest', () => {
  it('n envoie que productId et quantity, jamais un prix du client', () => {
    expect(toQuoteRequest(lines)).toEqual({ lines: [{ productId: 'tente', quantity: 2 }] });
  });
});

describe('fetchCartQuote', () => {
  it('poste le panier a la passerelle et convertit le devis en euros', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(apiQuote));

    const result = await fetchCartQuote(lines, fetchMock);

    expect(fetchMock.mock.calls[0][0]).toBe('/api/shop/cart/quote');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      lines: [{ productId: 'tente', quantity: 2 }],
    });
    expect(result).toEqual({
      ok: true,
      quote: {
        lines: [
          {
            productId: 'tente',
            unitPriceEur: 329,
            quantity: 2,
            lineTotalEur: 658,
            status: 'insufficient_stock',
            availableQuantity: 1,
          },
        ],
        subtotalEur: 658,
        shippingEur: 0,
        totalEur: 658,
        freeShippingThresholdEur: 80,
        amountRemainingForFreeShippingEur: 0,
        hasIssues: true,
      },
    });
  });

  it('ne contacte pas le serveur pour un panier vide', async () => {
    const fetchMock = vi.fn();

    const result = await fetchCartQuote([], fetchMock);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result).toMatchObject({ ok: true, quote: { lines: [], totalEur: 0, hasIssues: false } });
  });

  it('retourne ok:false sur une erreur HTTP, un reseau coupe ou un corps inattendu', async () => {
    const http = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Requete invalide.' }, 422));
    const network = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
    const body = vi.fn().mockResolvedValue(jsonResponse({ nope: true }));

    expect(await fetchCartQuote(lines, http)).toEqual({ ok: false });
    expect(await fetchCartQuote(lines, network)).toEqual({ ok: false });
    expect(await fetchCartQuote(lines, body)).toEqual({ ok: false });
  });
});
