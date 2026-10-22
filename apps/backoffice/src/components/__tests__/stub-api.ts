import { vi } from 'vitest';
import type { Product } from '@/lib/catalog/types';

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** Remplace fetch : le gestionnaire rend [statut, corps] pour chaque appel ; les appels sont journalises. */
export function stubApi(handler: (call: Call) => [number, unknown]): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : (init?.body ?? null);
      const call = { method: init?.method ?? 'GET', path: String(url), body };
      calls.push(call);
      const [status, data] = handler(call);
      return new Response(JSON.stringify(data), { status });
    })
  );
  return calls;
}

export function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 'tente-tunnel',
    slug: 'tente-tunnel',
    name: 'Tente Tunnel',
    category: 'tentes',
    price_cents: 12990,
    compare_at_price_cents: null,
    short_description: 'Deux places',
    description: 'Une tente légère.',
    specs: { weight_grams: 2100 },
    stock: 12,
    availability: 'in_stock',
    image_keys: [],
    image_urls: [],
    version: 3,
    archived_at: null,
    ...overrides,
  };
}

export function page(items: Product[], total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}
