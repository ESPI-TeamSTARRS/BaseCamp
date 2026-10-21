import { z } from 'zod';

const LOOKUP_URL = '/api/shop/orders/lookup';
const REQUEST_TIMEOUT_MS = 10000;
const ORDER_NUMBER = /^BC-[A-Z0-9]{10}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const STATUS_LABELS: Record<string, string> = {
  pending_payment: 'En attente de paiement',
  paid: 'Payée',
  expired: 'Expirée',
};
const UNKNOWN_STATUS_LABEL = 'Statut en cours de mise à jour';

const ApiOrderSchema = z.object({
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

export interface TrackedLine {
  name: string;
  unitPriceEur: number;
  quantity: number;
  lineTotalEur: number;
}

export interface TrackedOrder {
  number: string;
  status: string;
  statusLabel: string;
  lines: TrackedLine[];
  subtotalEur: number;
  shippingEur: number;
  totalEur: number;
  createdAt: string;
}

export type LookupResult =
  { ok: true; order: TrackedOrder } | { ok: false; reason: 'invalid' | 'not_found' | 'unavailable' };

type FetchLike = typeof fetch;
const toEur = (cents: number) => cents / 100;

export function isOrderNumber(value: string): boolean {
  return ORDER_NUMBER.test(value);
}

export function orderStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? UNKNOWN_STATUS_LABEL;
}

/**
 * Retrouve une commande par numéro et email. « Introuvable » couvre aussi un email faux : le
 * serveur ne les distingue pas, le front non plus.
 */
export async function lookupOrder(
  orderNumber: string,
  email: string,
  fetchImpl: FetchLike = fetch
): Promise<LookupResult> {
  const number = orderNumber.trim().toUpperCase();
  const address = email.trim();
  if (!isOrderNumber(number) || !EMAIL.test(address)) return { ok: false, reason: 'invalid' };
  try {
    const response = await fetchImpl(LOOKUP_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderNumber: number, email: address }),
      cache: 'no-store',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.status === 404) return { ok: false, reason: 'not_found' };
    if (response.status === 422) return { ok: false, reason: 'invalid' };
    if (!response.ok) return { ok: false, reason: 'unavailable' };
    const raw = ApiOrderSchema.parse(await response.json());
    return {
      ok: true,
      order: {
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
      },
    };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}
