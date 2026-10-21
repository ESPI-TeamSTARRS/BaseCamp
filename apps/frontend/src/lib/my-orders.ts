import { z } from 'zod';
import { orderStatusLabel, type TrackedOrder } from './order-lookup';

type FetchLike = typeof fetch;

const MY_ORDERS_URL = '/api/shop/me/orders';
const REQUEST_TIMEOUT_MS = 10000;
const PAGE_SIZE = 20;
const STATUS_UNAUTHORIZED = 401;
const toEur = (cents: number) => cents / 100;

const ApiOrderSchema = z.object({
  id: z.string(),
  number: z.string(),
  status: z.string(),
  lines: z.array(
    z.object({
      name: z.string(),
      unit_price_cents: z.number().int(),
      quantity: z.number().int(),
      line_total_cents: z.number().int(),
    })
  ),
  subtotal_cents: z.number().int(),
  shipping_cents: z.number().int(),
  total_cents: z.number().int(),
  created_at: z.string(),
});

const ApiPageSchema = z.object({ items: z.array(ApiOrderSchema), total: z.number().int() });

export interface MyOrder extends TrackedOrder {
  id: string;
}

export type MyOrdersResult =
  { ok: true; orders: MyOrder[]; total: number } | { ok: false; reason: 'unauthenticated' | 'unavailable' };

/**
 * Commandes du client connecté (le serveur ne renvoie que les siennes). Le jeton d'accès n'est ni
 * stocké ni journalisé ici : il vient de la mémoire du module `session-store`. Un 401 veut dire
 * « session à rafraîchir ou à rouvrir », tout le reste « réessayez ».
 */
export async function fetchMyOrders(
  accessToken: string,
  fetchImpl: FetchLike = fetch
): Promise<MyOrdersResult> {
  try {
    const response = await fetchImpl(`${MY_ORDERS_URL}?limit=${PAGE_SIZE}&offset=0`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.status === STATUS_UNAUTHORIZED) return { ok: false, reason: 'unauthenticated' };
    if (!response.ok) return { ok: false, reason: 'unavailable' };
    const page = ApiPageSchema.parse(await response.json());
    return {
      ok: true,
      total: page.total,
      orders: page.items.map((raw) => ({
        id: raw.id,
        number: raw.number,
        status: raw.status,
        statusLabel: orderStatusLabel(raw.status),
        lines: raw.lines.map((line) => ({
          name: line.name,
          unitPriceEur: toEur(line.unit_price_cents),
          quantity: line.quantity,
          lineTotalEur: toEur(line.line_total_cents),
        })),
        subtotalEur: toEur(raw.subtotal_cents),
        shippingEur: toEur(raw.shipping_cents),
        totalEur: toEur(raw.total_cents),
        createdAt: raw.created_at,
      })),
    };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}
