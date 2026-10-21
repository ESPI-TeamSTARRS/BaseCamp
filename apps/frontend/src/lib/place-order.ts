import { z } from 'zod';
import type { CartLine } from './cart-lines';
import type { OrderForm } from './order-form';

const ORDERS_URL = '/api/shop/orders';
const REQUEST_TIMEOUT_MS = 10000;
const GENERIC_INVALID_MESSAGE =
  'Votre commande ne peut pas être enregistrée. Vérifiez les informations saisies.';

const ApiOrderSchema = z.object({
  id: z.string(),
  number: z.string(),
  total_cents: z.number().int(),
});

export interface PlacedOrder {
  id: string;
  number: string;
  totalEur: number;
  /** true : la même clé a été rejouée, la commande existait déjà (pas de doublon). */
  replayed: boolean;
}

export type PlaceOrderResult =
  | { ok: true; order: PlacedOrder }
  | { ok: false; reason: 'stock' }
  | { ok: false; reason: 'invalid'; message: string }
  | { ok: false; reason: 'unavailable' };

type FetchLike = typeof fetch;

/** Seuls l'identifiant et la quantité des produits partent au serveur : jamais un prix. */
export function toOrderRequest(lines: CartLine[], form: OrderForm) {
  return {
    email: form.email,
    shippingAddress: {
      fullName: form.fullName,
      line1: form.line1,
      ...(form.line2 ? { line2: form.line2 } : {}),
      postalCode: form.postalCode,
      city: form.city,
      country: form.country,
    },
    lines: lines.map((line) => ({ productId: line.product.id, quantity: line.quantity })),
  };
}

async function invalidMessage(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  const isFixedMessage = typeof detail === 'string' && detail !== 'Requete invalide.';
  return isFixedMessage ? detail : GENERIC_INVALID_MESSAGE;
}

export async function placeOrder(
  lines: CartLine[],
  form: OrderForm,
  idempotencyKey: string,
  fetchImpl: FetchLike = fetch
): Promise<PlaceOrderResult> {
  try {
    const response = await fetchImpl(ORDERS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(toOrderRequest(lines, form)),
      cache: 'no-store',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.status === 409) return { ok: false, reason: 'stock' };
    if (response.status === 422)
      return { ok: false, reason: 'invalid', message: await invalidMessage(response) };
    if (!response.ok) return { ok: false, reason: 'unavailable' };
    const raw = ApiOrderSchema.parse(await response.json());
    return {
      ok: true,
      order: {
        id: raw.id,
        number: raw.number,
        totalEur: raw.total_cents / 100,
        replayed: response.status === 200,
      },
    };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}

/**
 * Une clé par contenu de commande : un nouvel essai identique (réseau coupé, double clic) la réutilise
 * et le serveur renvoie la même commande ; un contenu modifié reçoit une nouvelle clé.
 */
export class IdempotencyKeys {
  private fingerprint = '';
  private key = '';

  constructor(private readonly generate: () => string = () => crypto.randomUUID()) {}

  keyFor(lines: CartLine[], form: OrderForm): string {
    const fingerprint = JSON.stringify(toOrderRequest(lines, form));
    if (fingerprint !== this.fingerprint || this.key === '') {
      this.fingerprint = fingerprint;
      this.key = this.generate();
    }
    return this.key;
  }
}
