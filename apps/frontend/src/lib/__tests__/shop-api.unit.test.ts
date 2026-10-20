import { describe, expect, it, vi } from 'vitest';
import { fetchAllProducts, fetchProductBySlug, mapApiProduct } from '../shop-api';

const apiProduct = {
  id: 'tente-a',
  slug: 'tente-a',
  name: 'Tente A',
  category: 'tentes',
  price_cents: 32900,
  compare_at_price_cents: 38900,
  short_description: 'Resume',
  description: 'Description',
  thumbnail_url: '/media/tente-a-1.svg',
  image_urls: ['/media/tente-a-1.svg', '/media/tente-a-2.svg'],
  specs: {
    weight_grams: 1480,
    waterproofing_mm: 3000,
    comfort_temp_c: -5,
    seasons: 3,
    capacity_liters: null,
    material: 'Nylon',
  },
  rating_value: 4.8,
  rating_count: 132,
  availability: 'in_stock',
};

function pageOf(items: unknown[], page: number, total: number) {
  return { items, page, page_size: 50, total };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('mapApiProduct', () => {
  it('convertit les centimes entiers en euros et les cles snake_case', () => {
    const product = mapApiProduct(apiProduct as never);

    expect(product.priceEur).toBe(329);
    expect(product.compareAtPriceEur).toBe(389);
    expect(product.images).toEqual(['/media/tente-a-1.svg', '/media/tente-a-2.svg']);
    expect(product.specs).toMatchObject({
      weightGrams: 1480,
      waterproofingMm: 3000,
      comfortTempC: -5,
      seasons: 3,
    });
    expect(product.specs.capacityLiters).toBeUndefined();
    expect(product.ratingValue).toBe(4.8);
    expect(product.availability).toBe('in_stock');
  });

  it('laisse compareAtPriceEur indefini sans prix barre', () => {
    const product = mapApiProduct({ ...apiProduct, compare_at_price_cents: null } as never);

    expect(product.compareAtPriceEur).toBeUndefined();
  });
});

describe('fetchAllProducts', () => {
  it('appelle l API shop avec la categorie et retourne les produits', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(pageOf([apiProduct], 1, 1)));

    const result = await fetchAllProducts('tentes', fetchMock);

    expect(result.ok).toBe(true);
    expect(result.ok && result.products.map((p) => p.slug)).toEqual(['tente-a']);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/products?');
    expect(url).toContain('category=tentes');
  });

  it('parcourt toutes les pages', async () => {
    const second = { ...apiProduct, id: 'b', slug: 'b' };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(pageOf([apiProduct], 1, 2)))
      .mockResolvedValueOnce(jsonResponse(pageOf([second], 2, 2)));

    const result = await fetchAllProducts(undefined, fetchMock);

    expect(result.ok && result.products.map((p) => p.slug)).toEqual(['tente-a', 'b']);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('retourne ok:false quand l API est arretee', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('fetch failed'));

    expect(await fetchAllProducts(undefined, fetchMock)).toEqual({ ok: false });
  });

  it('retourne ok:false sur une reponse HTTP en erreur', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'boom' }, 503));

    expect(await fetchAllProducts(undefined, fetchMock)).toEqual({ ok: false });
  });

  it('retourne ok:false sur un corps inattendu', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ nope: true }));

    expect(await fetchAllProducts(undefined, fetchMock)).toEqual({ ok: false });
  });
});

describe('fetchProductBySlug', () => {
  it('appelle la fiche detail de l API et retourne le produit', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(apiProduct));

    const result = await fetchProductBySlug('tente-a', fetchMock);

    expect(result).toMatchObject({ ok: true, product: { slug: 'tente-a', priceEur: 329 } });
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/products\/tente-a$/);
  });

  it('encode le slug dans l URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Produit introuvable.' }, 404));

    await fetchProductBySlug('../etc/passwd?x=1', fetchMock);

    expect(String(fetchMock.mock.calls[0][0])).toContain('/products/..%2Fetc%2Fpasswd%3Fx%3D1');
  });

  it('retourne product:null sur un 404', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Produit introuvable.' }, 404));

    expect(await fetchProductBySlug('inconnu', fetchMock)).toEqual({ ok: true, product: null });
  });

  it('retourne ok:false quand l API est arretee', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('down'));

    expect(await fetchProductBySlug('tente-a', fetchMock)).toEqual({ ok: false });
  });

  it('retourne ok:false sur une erreur serveur ou un corps inattendu', async () => {
    const serverError = vi.fn().mockResolvedValue(jsonResponse({ detail: 'boom' }, 500));
    const badBody = vi.fn().mockResolvedValue(jsonResponse({ nope: true }));

    expect(await fetchProductBySlug('tente-a', serverError)).toEqual({ ok: false });
    expect(await fetchProductBySlug('tente-a', badBody)).toEqual({ ok: false });
  });
});
