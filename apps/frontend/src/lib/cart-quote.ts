import { z } from 'zod';
import type { CartLine } from './cart-lines';

const QUOTE_URL = '/api/shop/cart/quote';
const REQUEST_TIMEOUT_MS = 5000;

const ApiQuoteSchema = z.object({
  lines: z.array(
    z.object({
      product_id: z.string(),
      unit_price_cents: z.number().int(),
      quantity: z.number().int(),
      line_total_cents: z.number().int(),
      status: z.enum(['ok', 'insufficient_stock']),
      available_quantity: z.number().int(),
    })
  ),
  subtotal_cents: z.number().int(),
  shipping_cents: z.number().int(),
  total_cents: z.number().int(),
  free_shipping_threshold_cents: z.number().int(),
  amount_remaining_for_free_shipping_cents: z.number().int(),
  has_issues: z.boolean(),
});

export interface QuoteLine {
  productId: string;
  unitPriceEur: number;
  quantity: number;
  lineTotalEur: number;
  status: 'ok' | 'insufficient_stock';
  availableQuantity: number;
}

/** Devis établi par le serveur : seul lui décide des prix, de la livraison et du stock. */
export interface CartQuote {
  lines: QuoteLine[];
  subtotalEur: number;
  shippingEur: number;
  totalEur: number;
  freeShippingThresholdEur: number;
  amountRemainingForFreeShippingEur: number;
  hasIssues: boolean;
}

export type QuoteResult = { ok: true; quote: CartQuote } | { ok: false };
type FetchLike = typeof fetch;

/** Seuls l'identifiant et la quantité partent au serveur : jamais un prix venant du navigateur. */
export function toQuoteRequest(lines: CartLine[]) {
  return { lines: lines.map((line) => ({ productId: line.product.id, quantity: line.quantity })) };
}

const toEur = (cents: number) => cents / 100;

export async function fetchCartQuote(lines: CartLine[], fetchImpl: FetchLike = fetch): Promise<QuoteResult> {
  if (lines.length === 0) {
    return {
      ok: true,
      quote: {
        lines: [],
        subtotalEur: 0,
        shippingEur: 0,
        totalEur: 0,
        freeShippingThresholdEur: 0,
        amountRemainingForFreeShippingEur: 0,
        hasIssues: false,
      },
    };
  }
  try {
    const response = await fetchImpl(QUOTE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(toQuoteRequest(lines)),
      cache: 'no-store',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) return { ok: false };
    const raw = ApiQuoteSchema.parse(await response.json());
    return {
      ok: true,
      quote: {
        lines: raw.lines.map((line) => ({
          productId: line.product_id,
          unitPriceEur: toEur(line.unit_price_cents),
          quantity: line.quantity,
          lineTotalEur: toEur(line.line_total_cents),
          status: line.status,
          availableQuantity: line.available_quantity,
        })),
        subtotalEur: toEur(raw.subtotal_cents),
        shippingEur: toEur(raw.shipping_cents),
        totalEur: toEur(raw.total_cents),
        freeShippingThresholdEur: toEur(raw.free_shipping_threshold_cents),
        amountRemainingForFreeShippingEur: toEur(raw.amount_remaining_for_free_shipping_cents),
        hasIssues: raw.has_issues,
      },
    };
  } catch {
    return { ok: false };
  }
}
