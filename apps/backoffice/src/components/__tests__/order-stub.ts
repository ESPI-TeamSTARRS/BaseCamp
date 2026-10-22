import type { OrderDetail, OrderSummary } from '@/lib/orders/types';

export function makeSummary(overrides: Partial<OrderSummary> = {}): OrderSummary {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    number: 'BC-1001',
    status: 'paid',
    email: 'camille.martin@example.org',
    total_cents: 8290,
    item_count: 2,
    created_at: '2026-10-20T10:00:00Z',
    ...overrides,
  };
}

export function ordersPage(items: OrderSummary[], total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}

export function makeDetail(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    number: 'BC-1001',
    status: 'paid',
    email: 'camille.martin@example.org',
    shipping_address: {
      full_name: 'Camille Martin',
      line1: '12 rue des Alpes',
      line2: 'Bâtiment B',
      postal_code: '38000',
      city: 'Grenoble',
      country: 'FR',
    },
    lines: [{ name: 'Popote', unit_price_cents: 3900, quantity: 2, line_total_cents: 7800 }],
    subtotal_cents: 7800,
    shipping_cents: 490,
    total_cents: 8290,
    created_at: '2026-10-20T10:00:00Z',
    ...overrides,
  };
}
