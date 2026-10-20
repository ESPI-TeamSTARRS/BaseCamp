import { z } from 'zod';
import { isProductCategory } from './categories';
import type { Product, ProductCategory } from '../types/product';

const PAGE_SIZE = 50;
const REQUEST_TIMEOUT_MS = 3000;
const MAX_PAGES = 20;

const nullableNumber = z.number().nullish();

const ApiProductSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  category: z.string().refine(isProductCategory),
  price_cents: z.number().int().positive(),
  compare_at_price_cents: nullableNumber,
  short_description: z.string(),
  description: z.string(),
  image_urls: z.array(z.string()),
  specs: z.object({
    weight_grams: nullableNumber,
    waterproofing_mm: nullableNumber,
    comfort_temp_c: nullableNumber,
    seasons: nullableNumber,
    capacity_liters: nullableNumber,
    material: z.string().nullish(),
  }),
  rating_value: z.number(),
  rating_count: z.number().int(),
  availability: z.enum(['in_stock', 'low_stock', 'out_of_stock']),
});

const ApiPageSchema = z.object({
  items: z.array(ApiProductSchema),
  page: z.number().int(),
  total: z.number().int(),
});

type ApiProduct = z.infer<typeof ApiProductSchema>;

export type CatalogResult = { ok: true; products: Product[] } | { ok: false };
export type ProductResult = { ok: true; product: Product | null } | { ok: false };
type FetchLike = typeof fetch;

function shopApiUrl(): string {
  // URL interne (réseau Docker), lue côté serveur uniquement : jamais exposée au navigateur.
  return (process.env.SHOP_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
}

function defined<T>(value: T | null | undefined): T | undefined {
  return value ?? undefined;
}

export function mapApiProduct(raw: ApiProduct): Product {
  return {
    id: raw.id,
    slug: raw.slug,
    name: raw.name,
    category: raw.category as ProductCategory,
    priceEur: raw.price_cents / 100,
    compareAtPriceEur: raw.compare_at_price_cents ? raw.compare_at_price_cents / 100 : undefined,
    shortDescription: raw.short_description,
    description: raw.description,
    images: raw.image_urls,
    specs: {
      weightGrams: defined(raw.specs.weight_grams),
      waterproofingMm: defined(raw.specs.waterproofing_mm),
      comfortTempC: defined(raw.specs.comfort_temp_c),
      seasons: defined(raw.specs.seasons) as Product['specs']['seasons'],
      capacityLiters: defined(raw.specs.capacity_liters),
      material: defined(raw.specs.material),
    },
    availability: raw.availability,
    ratingValue: raw.rating_value,
    ratingCount: raw.rating_count,
  };
}

async function fetchPage(category: ProductCategory | undefined, page: number, fetchImpl: FetchLike) {
  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (category) query.set('category', category);
  const response = await fetchImpl(`${shopApiUrl()}/products?${query}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`shop API: ${response.status}`);
  return ApiPageSchema.parse(await response.json());
}

/** Charge le catalogue (toutes les pages). Jamais d'exception : `ok: false` si l'API est indisponible. */
export async function fetchAllProducts(
  category?: ProductCategory,
  fetchImpl: FetchLike = fetch
): Promise<CatalogResult> {
  try {
    const products: Product[] = [];
    for (let page = 1; page <= MAX_PAGES; page += 1) {
      const result = await fetchPage(category, page, fetchImpl);
      products.push(...result.items.map(mapApiProduct));
      if (result.items.length === 0 || products.length >= result.total) break;
    }
    return { ok: true, products };
  } catch {
    // Détail volontairement non remonté : l'interface affiche un message générique.
    return { ok: false };
  }
}

export async function fetchProductBySlug(slug: string, fetchImpl: FetchLike = fetch): Promise<ProductResult> {
  const catalog = await fetchAllProducts(undefined, fetchImpl);
  if (!catalog.ok) return { ok: false };
  return { ok: true, product: catalog.products.find((p) => p.slug === slug) ?? null };
}
